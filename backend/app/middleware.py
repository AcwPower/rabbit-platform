import json, time, hmac, secrets
from datetime import timedelta
from fastapi import Request
from starlette.responses import JSONResponse, Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from .db import Session, now
from .models import RateBucket, RequestKey, LoginSession
from .security import digest, cipher
from .config import settings

def error(code,message,status):
    return JSONResponse({'error':{'code':code,'message':message}},status_code=status)

def rate_limit(ip, group, limit):
    window=int(time.time())//60
    key=digest(f'{ip}:{group}:{window}')
    for _ in range(3):
        try:
            with Session.begin() as db:
                row=db.scalar(select(RateBucket).where(RateBucket.id==key).with_for_update())
                if row is None:
                    db.add(RateBucket(id=key,count=1,expires_at=now()+timedelta(minutes=2)))
                elif row.count>=limit:
                    return False
                else: row.count+=1
            return True
        except IntegrityError: continue
    return False

def without_contacts(value):
    # Contact authorization and deletion are evaluated afresh by detail GETs.
    # Never retain contact details in an idempotency response snapshot.
    if isinstance(value, dict):
        return {k: None if k in ('contact','contacts','public_contact') else without_contacts(v) for k,v in value.items()}
    if isinstance(value, list): return [without_contacts(v) for v in value]
    return value

async def guard(request: Request, call_next):
    path=request.url.path
    if path=='/api/health': return await call_next(request)
    write=request.method in ('POST','PUT','PATCH','DELETE')
    notification_query=request.method=='POST' and path in ('/api/notifications/query','/api/boss/bookings/query')
    group='auth' if path.startswith('/api/auth/') else 'write' if write and not notification_query else 'read'
    if not rate_limit(request.client.host, group, {'auth':15,'write':45,'read':240}[group]):
        return error('RATE_LIMITED','操作过于频繁，请稍后重试',429)
    if write:
        if request.headers.get('origin')!=settings.public_origin.rstrip('/'):
            return error('ORIGIN_REJECTED','请求来源不被允许',403)
        session_token=request.cookies.get('rabbit_session')
        if session_token:
            with Session() as db:
                session=db.get(LoginSession,digest(session_token))
                if session and session.expires_at>now() and not hmac.compare_digest(session.csrf,request.headers.get('x-csrf-token','')):
                    return error('CSRF_REJECTED','页面验证已失效，请刷新后重试',403)
        if int(request.headers.get('content-length','0') or '0') > 6*1024*1024:
            return error('FILE_TOO_LARGE','上传文件不得超过 5 MB',413)
    key=None
    if write and not notification_query and not path.startswith('/api/auth/'):
        raw=request.headers.get('x-idempotency-key','')
        if len(raw)<16 or len(raw)>100:
            return error('IDEMPOTENCY_REQUIRED','缺少请求标识，请刷新页面',400)
        scope=request.cookies.get('rabbit_session') or request.headers.get('x-manage-token') or request.client.host
        key=digest(scope+':'+path+':'+raw)
        body=await request.body()
        fingerprint=digest(request.method+':'+body.hex())
        try:
            with Session.begin() as db:
                db.add(RequestKey(key_hash=key,request_hash=fingerprint))
        except IntegrityError:
            with Session() as db:
                old=db.get(RequestKey,key)
                if not old or old.request_hash!=fingerprint:
                    return error('IDEMPOTENCY_CONFLICT','请求标识被重复使用',409)
                if not old.status_code:
                    return error('REQUEST_PENDING','请求仍在处理中，请稍后重试',409)
                return Response(cipher.decrypt(old.response.encode()),status_code=old.status_code,media_type='application/json',headers={'Cache-Control':'no-store'})
    try:
        response=await call_next(request)
        if key:
            payload=b''.join([chunk async for chunk in response.body_iterator])
            with Session.begin() as db:
                old=db.get(RequestKey,key)
                if response.status_code<400:
                    old.status_code=response.status_code
                    safe_payload=json.dumps(without_contacts(json.loads(payload)),ensure_ascii=False).encode()
                    old.response=cipher.encrypt(safe_payload).decode()
                else: db.delete(old)
            response=Response(payload,status_code=response.status_code,headers=dict(response.headers),media_type=response.media_type)
        response.headers['Cache-Control']='no-store'
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Request-ID']=secrets.token_hex(8)
        return response
    except Exception:
        if key:
            with Session.begin() as db:
                old=db.get(RequestKey,key)
                if old: db.delete(old)
        raise
