import re, secrets, smtplib, hmac
from email.message import EmailMessage
from datetime import timedelta
from fastapi import APIRouter, Request, Depends
from sqlalchemy import select
from .config import settings
from .db import get_db, now
from .models import Recovery
from .schemas import RecoveryInput
from .security import cipher, digest, fail, require_owner, manager_token, audit
from .services import get_card, get_application

router=APIRouter()

def resource(data,db):
    return get_card(db,'boss',data.resource_id,True) if data.resource=='boss' else get_application(db,data.resource_id,True)

def authorize(data,request,db):
    obj=resource(data,db)
    attr='owner_id' if data.resource=='boss' else 'applicant_id'
    require_owner(request,db,obj,attr)
    if getattr(obj,attr): fail('ACCOUNT_RESOURCE','账号记录请通过登录管理')
    return obj

def send_code(email,code):
    msg=EmailMessage(); msg['Subject']='小白兔组队 · 管理凭证验证'
    msg['From']=settings.smtp_from; msg['To']=email
    msg.set_content(f'你的验证码是 {code}，10 分钟内有效。如非本人操作，请忽略。请勿向他人透露验证码。')
    try:
        with smtplib.SMTP(settings.smtp_host,settings.smtp_port,timeout=10) as smtp:
            if settings.smtp_starttls: smtp.starttls()
            if settings.smtp_user: smtp.login(settings.smtp_user,settings.smtp_password)
            smtp.send_message(msg)
    except Exception: fail('EMAIL_UNAVAILABLE','邮件暂时无法发送，请稍后重试',503)

@router.post('/recovery/{action}')
def recovery(action:str,data:RecoveryInput,request:Request,db=Depends(get_db)):
    if not settings.smtp_host or not settings.smtp_from:
        fail('EMAIL_NOT_CONFIGURED','邮件恢复尚未开通，请妥善保存管理链接',503)
    row=db.scalar(select(Recovery).where(Recovery.resource==data.resource,Recovery.resource_id==data.resource_id).with_for_update())
    if action=='bind':
        authorize(data,request,db)
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',data.email): fail('INVALID_EMAIL','邮箱格式不正确')
        if row and row.expires_at and row.expires_at>now()+timedelta(minutes=9): fail('RATE_LIMITED','请一分钟后再试',429)
        if row is None: row=Recovery(resource=data.resource,resource_id=data.resource_id); db.add(row)
        row.email_encrypted=cipher.encrypt(data.email.encode()).decode(); row.email_hash=digest(data.email.lower())
        row.verified=False
        code=str(secrets.randbelow(900000)+100000); row.code_hash=digest(code); row.attempts=0; row.expires_at=now()+timedelta(minutes=10)
        send_code(data.email,code)
    elif action=='send':
        if row and row.verified and hmac.compare_digest(row.email_hash,digest(data.email.lower())):
            if row.expires_at and row.expires_at>now()+timedelta(minutes=9): return {'ok':True}
            code=str(secrets.randbelow(900000)+100000); row.code_hash=digest(code); row.attempts=0; row.expires_at=now()+timedelta(minutes=10)
            send_code(cipher.decrypt(row.email_encrypted.encode()).decode(),code)
    elif action in ('verify','recover'):
        if action=='verify': authorize(data,request,db)
        if not row or not row.code_hash or not row.expires_at or row.expires_at<=now() or row.attempts>=5:
            fail('CODE_EXPIRED','验证码无效或已过期')
        row.attempts+=1
        if not hmac.compare_digest(row.code_hash,digest(data.code)):
            db.commit(); fail('CODE_WRONG','验证码不正确')
        if action=='recover':
            if not row.verified: fail('UNVERIFIED_EMAIL','此邮箱尚未完成绑定')
            obj=resource(data,db); obj.manage_hash=digest(manager_token(request,True))
            audit(db,request,'credential_recovered',f'{data.resource}:{data.resource_id}')
        row.verified=True; row.code_hash=None
    else: fail('INVALID_ACTION','不支持的操作')
    return {'ok':True}
