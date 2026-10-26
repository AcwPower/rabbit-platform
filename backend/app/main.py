import io, json, secrets, hmac, logging, re, base64, hashlib
from datetime import timedelta, timezone
from decimal import Decimal
from typing import Literal
import httpx
from fastapi import FastAPI, Depends, Request, Response, UploadFile, File, Form, HTTPException, Query
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import select, or_, func, text, case
from sqlalchemy.exc import IntegrityError
from PIL import Image, UnidentifiedImageError
from pydantic import ValidationError
from .config import settings
from .db import get_db, now
from .models import *
from .schemas import *
from .security import *
from .services import *
from .middleware import guard
from .ocr_regions import validate_regions
from .registration import prepare_screenshot, review_screenshot, MAX_UPLOAD
from .map_names import POPULAR_MAPS,map_key,map_options
from .team_recruitment import sync_recruitment,close_recruitment,delete_recruitment_contact
from .profiles import account_contact
from .application_events import notify_application
from .schedule import boss_requested_window

app=FastAPI(title='小白兔组队 API',version='1.0.0',docs_url=None,redoc_url=None,openapi_url=None)
app.middleware('http')(guard)

@app.exception_handler(HTTPException)
async def api_error(request,exc):
    detail=exc.detail if isinstance(exc.detail,dict) else {'code':'ERROR','message':str(exc.detail)}
    return JSONResponse({'error':detail},status_code=exc.status_code)

@app.exception_handler(RequestValidationError)
async def validation_error(request,exc):
    errors=[{'field':'.'.join(str(x) for x in e['loc'][1:]),'message':e['msg']} for e in exc.errors()]
    return JSONResponse({'error':{'code':'VALIDATION_ERROR','message':'请检查填写内容','fields':errors}},status_code=422)

@app.exception_handler(IntegrityError)
async def integrity_error(request,exc):
    return JSONResponse({'error':{'code':'CONFLICT','message':'记录已存在或状态冲突，请刷新后重试'}},status_code=409)

@app.get('/api/health')
def health(db=Depends(get_db)):
    db.execute(text('SELECT 1'))
    return {'status':'ok','version':'1.0.0'}

@app.get('/api/meta')
def meta(db=Depends(get_db)):
    team_count=db.scalar(select(func.count(TeamCard.id)).where(TeamCard.status=='active',TeamCard.expires_at>now()))
    boss_count=db.scalar(select(func.count(BossCard.id)).where(BossCard.status=='active',BossCard.expires_at>now()))
    partner_count=db.scalar(select(func.count(PartnerCard.id)).where(PartnerCard.status=='active',PartnerCard.expires_at>now())) if settings.teammate_recruitment_enabled else 0
    maps=set(db.scalars(select(TeamCard.map_name).where(TeamCard.status=='active')).all()+db.scalars(select(BossCard.map_name).where(BossCard.status=='active')).all())
    if settings.teammate_recruitment_enabled:maps.update(db.scalars(select(PartnerCard.map_name).where(PartnerCard.status=='active',PartnerCard.map_name!='')).all())
    return {'teams':team_count,'bosses':boss_count,'partners':partner_count,'timezone':'Asia/Shanghai','email_recovery':bool(settings.smtp_host and settings.smtp_from),
        'maps':map_options(maps),'features':{'teammate_recruitment':settings.teammate_recruitment_enabled}}

@app.get('/api/challenge')
def challenge(db=Depends(get_db)):
    a,b=secrets.randbelow(20)+1,secrets.randbelow(9)+1
    key=secrets.token_urlsafe(24)
    db.add(Challenge(id=key,answer_hash=digest(key+':'+str(a+b)),expires_at=now()+timedelta(minutes=10)))
    return {'id':key,'question':f'{a} + {b} = ?'}

def set_session(response,db,user):
    token=secrets.token_urlsafe(32); csrf=secrets.token_urlsafe(32)
    db.add(LoginSession(token_hash=digest(token),user_id=user.id,csrf=csrf,expires_at=now()+timedelta(days=14)))
    response.set_cookie('rabbit_session',token,max_age=14*86400,httponly=True,secure=settings.cookie_secure,samesite='lax',path='/party')
    return {'user':{'id':user.id,'username':user.username,'is_admin':user.is_admin,'created_at':iso(user.created_at)},'csrf':csrf}

@app.post('/api/auth/register')
async def register(request:Request,response:Response,credentials:str=Form(...),screenshot:UploadFile|None=File(None),db=Depends(get_db)):
    try: data=Credentials.model_validate_json(credentials)
    except ValidationError as exc:
        raise RequestValidationError([{**e,'loc':('body',*e['loc'])} for e in exc.errors()])
    if not screenshot: fail('CHARACTER_SCREENSHOT_REQUIRED','创建打手账号必须上传包含「角色能力」窗口的个人角色截图',422)
    verify_challenge(db,data.challenge_id,data.answer)
    # Consume the challenge before the expensive OCR call, including failed attempts.
    db.commit()
    if db.scalar(select(User.id).where(User.username==data.username)):
        fail('USERNAME_TAKEN','此用户名已被使用',409)
    raw=prepare_screenshot(await screenshot.read(MAX_UPLOAD+1))
    result=await review_screenshot(raw)
    user=User(username=data.username,password_hash=hash_password(data.password))
    db.add(user); db.flush()
    db.add(RegistrationProof(user_id=user.id,encrypted_image=cipher.encrypt(raw).decode(),
        game_id=result['game_id'],level=result['level'],job=result['job'],
        confidence=json.dumps(result['confidence']),image_hash=hashlib.sha256(raw).hexdigest()))
    db.add(Character(user_id=user.id,name=result['game_id'],level=result['level'],job=result['job']))
    audit(db,request,'register',f'user:{user.id}')
    audit(db,request,'registration_image_checked',f'user:{user.id}','角色截图自动格式校验通过；不代表身份或角色归属认证')
    return set_session(response,db,user)

@app.post('/api/auth/login')
def login(data:Credentials,request:Request,response:Response,db=Depends(get_db)):
    verify_challenge(db,data.challenge_id,data.answer)
    user=db.scalar(select(User).where(User.username==data.username))
    if not user or not check_password(data.password,user.password_hash):
        # Consume challenge even when login fails.
        db.commit(); fail('LOGIN_FAILED','用户名或密码不正确',401)
    if user.status!='active': fail('ACCOUNT_BANNED','账号已停用，可在防骗须知中提交申诉',403)
    return set_session(response,db,user)

@app.post('/api/auth/logout')
def logout(request:Request,response:Response,db=Depends(get_db)):
    row=db.get(LoginSession,digest(request.cookies.get('rabbit_session','')))
    if row: db.delete(row)
    response.delete_cookie('rabbit_session',path='/party')
    return {'ok':True}

@app.get('/api/auth/session')
def session(request:Request,db=Depends(get_db)):
    user=current_user(request,db)
    row=db.get(LoginSession,digest(request.cookies.get('rabbit_session','')))
    return {'user':{'id':user.id,'username':user.username,'is_admin':user.is_admin,'created_at':iso(user.created_at)} if user else None,'csrf':row.csrf if user else None}

@app.get('/api/me')
def me(request:Request,db=Depends(get_db)):
    user=current_user(request,db,True)
    teams=db.scalars(select(TeamCard).where(TeamCard.owner_id==user.id).order_by(TeamCard.created_at.desc()).limit(100)).all()
    bosses=db.scalars(select(BossCard).where(BossCard.owner_id==user.id).order_by(BossCard.created_at.desc()).limit(100)).all()
    incoming=db.scalars(select(Application).where(or_(Application.team_card_id.in_(select(TeamCard.id).where(TeamCard.owner_id==user.id)),Application.boss_card_id.in_(select(BossCard.id).where(BossCard.owner_id==user.id)))).order_by(Application.created_at.desc()).limit(100)).all()
    outgoing=db.scalars(select(Application).where(Application.applicant_id==user.id).order_by(Application.created_at.desc()).limit(100)).all()
    chars=db.scalars(select(Character).where(Character.user_id==user.id)).all()
    return {'cards':[card_dict(c,'team') for c in teams]+[card_dict(c,'boss') for c in bosses],
        'incoming':[app_dict(request,db,a) for a in incoming],'outgoing':[app_dict(request,db,a) for a in outgoing],
        'characters':[{'id':c.id,'name':c.name,'level':c.level,'job':c.job} for c in chars],
        'has_registration_proof':db.scalar(select(RegistrationProof.user_id).where(RegistrationProof.user_id==user.id)) is not None}

@app.get('/api/users/{user_id}/registration-proof')
def registration_proof(user_id:int,request:Request,db=Depends(get_db)):
    viewer=current_user(request,db,True)
    if viewer.id!=user_id and not viewer.is_admin: fail('FORBIDDEN','仅账号本人和管理员可查看注册截图',403)
    proof=db.get(RegistrationProof,user_id)
    if not proof: fail('NOT_FOUND','此账号未留存注册截图',404)
    if viewer.is_admin and viewer.id!=user_id:
        audit(db,request,'view_registration_image',f'user:{user_id}')
    return {'user_id':proof.user_id,'game_id':proof.game_id,'level':proof.level,'job':proof.job,
        'created_at':iso(proof.created_at),'image':'data:image/jpeg;base64,'+base64.b64encode(cipher.decrypt(proof.encrypted_image.encode())).decode()}

@app.post('/api/characters')
def create_character(data:CharacterInput,request:Request,db=Depends(get_db)):
    current_user(request,db,True)
    fail('CHARACTER_ADMIN_ONLY','角色资料仅管理员可修改，请在「我的资料」提交修改申请',403)

@app.delete('/api/characters/{char_id}')
def delete_character(char_id:int,request:Request,db=Depends(get_db)):
    current_user(request,db,True)
    fail('CHARACTER_ADMIN_ONLY','角色资料仅管理员可修改，请在「我的资料」提交修改申请',403)

@app.get('/api/{kind}-cards')
def list_cards(kind:Literal['team','boss'],q:str=Query('',max_length=80),map_name:str='',level:int|None=None,
        flower:str='',capacity:int|None=None,price_mode:str='',exp_min:int|None=None,exp_max:int|None=None,
        at_time:str='',available:bool=False,sort:Literal['availability','latest']='availability',
        page:int=Query(1,ge=1),db=Depends(get_db)):
    model=card_class(kind)
    conditions=[model.status=='active',model.expires_at>now()]
    if q: conditions.append(or_(model.map_name.contains(q,autoescape=True),model.game_id.contains(q,autoescape=True)))
    if map_name:
        # Keep older/manual names searchable after dropdown aliases are merged.
        names=db.scalars(select(model.map_name).where(model.status=='active',model.expires_at>now()).distinct()).all()
        aliases=[name for name in names if map_key(name)==map_key(map_name)]
        conditions.append(model.map_name.in_(aliases or [map_name]))
    if level:
        conditions.extend([model.level_min<=level,model.level_max>=level] if kind=='team' else [model.level==level])
    if flower: conditions.append(model.flower==flower)
    if capacity: conditions.append(model.capacity==capacity)
    if price_mode: conditions.append(model.price_mode==price_mode)
    if exp_min is not None: conditions.append(model.exp_max>=exp_min)
    if exp_max is not None: conditions.append(model.exp_min<=exp_max)
    if at_time:
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',at_time): fail('INVALID_TIME','时段格式不正确')
        conditions.append(or_((model.start_time<model.end_time)&(model.start_time<=at_time)&(model.end_time>=at_time),
            (model.start_time>=model.end_time)&or_(model.start_time<=at_time,model.end_time>=at_time)))
    if available and kind=='team':conditions.append(model.capacity>model.fighter_count+model.priest_count+model.confirmed_boss_count+case((model.teammate_need!='none',1),else_=0))
    total=db.scalar(select(func.count(model.id)).where(*conditions))
    query=select(model).where(*conditions)
    if kind=='team' and sort=='availability':
        # A scheduled end is only an estimate; overdue matches never free seats
        # automatically or jump to the front of the queue.
        next_end=select(Match.team_id,func.min(Match.expected_end_at).label('ends_at')).where(
            Match.status.in_(['boarded','disputed']),Match.boarded_at.is_not(None),
            Match.finished_at.is_(None),Match.expected_end_at>now()
        ).group_by(Match.team_id).subquery()
        free=model.capacity-model.fighter_count-model.priest_count-model.confirmed_boss_count-case((model.teammate_need!='none',1),else_=0)
        query=query.outerjoin(next_end,next_end.c.team_id==model.id).order_by(
            case((free>0,0),(next_end.c.ends_at.is_not(None),1),else_=2),
            case((free<=0,next_end.c.ends_at),else_=None))
    rows=db.scalars(query.order_by(model.created_at.desc(),model.id.desc()).offset((page-1)*20).limit(20)).all()
    progress=public_boss_progress(db,[c.id for c in rows]) if kind=='team' else {}
    items=[card_dict(c,kind) for c in rows]
    if kind=='team':
        for item in items:item['boss_progress']=progress[item['id']]
    return {'items':items,'total':total,'page':page,'has_more':page*20<total}

@app.get('/api/{kind}-cards/{card_id}')
def card_detail(kind:Literal['team','boss'],card_id:int,request:Request,db=Depends(get_db)):
    card=get_card(db,kind,card_id)
    owner=owns(request,db,card)
    if card.status=='hidden' and not owner: fail('NOT_FOUND','此卡片已被隐藏',404)
    result=card_dict(card,kind,db,True); result['is_owner']=owner
    if kind=='team':result['boss_progress']=public_boss_progress(db,[card.id])[card.id]
    if owner:
        result['contact']=read_contact(db,kind,card.id)
        condition=Application.team_card_id==card_id if kind=='team' else Application.boss_card_id==card_id
        result['applications']=[app_dict(request,db,a) for a in db.scalars(select(Application).where(condition).order_by(Application.created_at.desc()).limit(100))]
    return result

def write_card(kind,data,request,db,card=None):
    user=current_user(request,db,kind=='team')
    if not settings.teammate_recruitment_enabled and (data.teammate_need not in (None,'none') or data.teammate_level_min is not None or data.teammate_level_max is not None):
        fail('FEATURE_UNAVAILABLE','队友招募暂未开放，请刷新页面后重新发布',409)
    if card:
        require_owner(request,db,card)
        if card.price_currency!='rmb' and 'price_currency' not in data.model_fields_set:
            fail('CURRENCY_REQUIRED','请刷新页面，确认收费币种后再保存',409)
        if card.status in ('hidden','matched') or card.expires_at<=now(): fail('CARD_UNAVAILABLE','此卡片已结束，不能修改',409)
        if data.version!=card.version: fail('VERSION_CONFLICT','卡片刚刚被更新，请刷新后编辑',409)
    else:
        verify_challenge(db,data.challenge_id,data.answer)
        if user:
            active_count=db.scalar(select(func.count(card_class(kind).id)).where(card_class(kind).owner_id==user.id,card_class(kind).status=='active',card_class(kind).expires_at>now()))
            if active_count>=5: fail('LIMIT_REACHED','每种类型最多同时发布 5 张卡片')
        card=card_class(kind)(owner_id=user.id if user else None,manage_hash=None if user else digest(manager_token(request,True)))
        db.add(card)
    previous_need=(card.teammate_need or 'none') if kind=='team' else 'none'
    if kind=='team':
        card.teammate_need=data.teammate_need if data.teammate_need is not None else previous_need
        reserved=int(card.teammate_need!='none')
        if data.boss_slots is not None:data.capacity=data.boss_slots+data.fighter_count+data.priest_count+reserved
        if data.capacity>6:fail('CAPACITY_EXCEEDED','老板人数与队友配置合计超过游戏队伍上限，请减少老板人数',409)
        if data.flower=='any' or (data.flower=='none')!=(data.priest_count==0): fail('INVALID_FLOWER','花类型与祭司人数不一致')
        if data.fighter_count+data.priest_count+reserved+(card.confirmed_boss_count or 0)>data.capacity: fail('CAPACITY_EXCEEDED','需要的老板人数不能少于已确认上车人数',409)
        if data.price_mode=='any' or data.price is None: fail('PRICE_REQUIRED','招募卡必须填写收费模式和价格')
        for f in ('fighter_count','priest_count','level_min','level_max'): setattr(card,f,getattr(data,f))
    for f in ('game_id','level','map_name','capacity','flower','price_mode','price_currency','price','night_price','exp_min','exp_max','start_time','end_time','notes'):
        setattr(card,f,getattr(data,f))
    # Editing never extends expiry or changes created_at.
    if not card.id: card.expires_at=now()+timedelta(hours=data.duration_hours)
    else: card.version+=1
    db.flush()
    contact=account_contact(db,request,user,data.contact)
    save_contact(db,kind,card.id,contact,data.public_contact if kind=='team' else False,card.expires_at+timedelta(days=7))
    if kind=='team' and settings.teammate_recruitment_enabled:sync_recruitment(db,card,data,previous_need)
    audit(db,request,'card_saved',f'{kind}:{card.id}')
    return card_dict(card,kind,db)

@app.post('/api/{kind}-cards',status_code=201)
def create_card(kind:Literal['team','boss'],data:CardInput,request:Request,db=Depends(get_db)):
    return write_card(kind,data,request,db)

@app.put('/api/{kind}-cards/{card_id}')
def edit_card(kind:Literal['team','boss'],card_id:int,data:CardInput,request:Request,db=Depends(get_db)):
    return write_card(kind,data,request,db,get_card(db,kind,card_id,True))

@app.post('/api/{kind}-cards/{card_id}/status')
def change_card_status(kind:Literal['team','boss'],card_id:int,data:Action,request:Request,db=Depends(get_db)):
    card=get_card(db,kind,card_id,True); require_owner(request,db,card)
    if card.status=='hidden': fail('MODERATED','此卡片已被管理员隐藏，需申诉后处理',403)
    if data.action not in ('close','matched') or data.action=='matched' and kind!='boss': fail('INVALID_ACTION','不支持的操作')
    card.status='matched' if data.action=='matched' else 'closed'; card.version+=1
    if kind=='team':close_recruitment(db,card)
    audit(db,request,'card_'+card.status,f'{kind}:{card.id}')
    return {'ok':True}

@app.post('/api/applications',status_code=201)
def apply(data:ApplyInput,request:Request,db=Depends(get_db)):
    user=current_user(request,db,data.card_type=='boss')
    offered=None
    if data.card_type=='boss':
        if not data.offered_team_id: fail('TEAM_REQUIRED','请选择你发布的招募队伍')
        offered=get_card(db,'team',data.offered_team_id,True)
        require_owner(request,db,offered);ensure_active(offered)
    card=get_card(db,data.card_type,data.card_id,True)
    if data.card_type=='boss':ensure_boss_claimable(db,card)
    else:ensure_active(card)
    requested_start=data.requested_start_at.astimezone(timezone.utc).replace(tzinfo=None,microsecond=0) if data.requested_start_at else None
    if requested_start and not now()-timedelta(minutes=30)<=requested_start<=now()+timedelta(days=7):
        fail('INVALID_START_TIME','预计上车时间须在未来 7 天内；若选择此时，请更新后重试',422)
    if owns(request,db,card): fail('SELF_APPLY','不能申请自己的卡片',409)
    if data.card_type=='team' and not card.level_min<=data.level<=card.level_max: fail('LEVEL_MISMATCH','角色等级不在招募范围内')
    if data.card_type=='boss':
        if not offered.level_min<=card.level<=offered.level_max:fail('LEVEL_MISMATCH','老板等级不在队伍范围内',409)
        if card.flower=='active' and offered.flower!='active':fail('FLOWER_MISMATCH','求带要求活花',409)
    verify_challenge(db,data.challenge_id,data.answer)
    identity=f'{data.card_type}:{data.card_id}:{data.game_id.casefold()}'
    key=digest(identity)
    if db.scalar(select(Application.id).where(Application.active_key==key)):
        fail('DUPLICATE_APPLICATION','此角色已申请，请从“我的”查看原申请',409)
    row=Application(card_type=data.card_type,team_card_id=card.id if data.card_type=='team' else None,
        boss_card_id=card.id if data.card_type=='boss' else None,offered_team_id=data.offered_team_id if data.card_type=='boss' else None,
        applicant_id=user.id if user else None,manage_hash=None if user else digest(manager_token(request,True)),active_key=key,
        game_id=data.game_id,level=data.level,notes=data.notes,requested_start_at=requested_start,duration_hours=data.duration_hours,
        expires_at=min(now()+timedelta(hours=24),card.expires_at))
    db.add(row); db.flush()
    save_contact(db,'application',row.id,account_contact(db,request,user,data.contact),expires=card.expires_at+timedelta(days=7))
    if data.card_type=='boss':
        row.status='accepted';card.status='matched';card.version+=1
        if requested_start:
            planned_start, planned_end = requested_start, requested_start+timedelta(hours=data.duration_hours)
        else:
            planned_start, planned_end = boss_requested_window(now(), card.start_time, card.end_time)
        db.add(Match(application_id=row.id,team_id=offered.id,planned_start_at=planned_start,
            expected_end_at=planned_end))
        # Older pending intents cannot reveal the same boss's contact later.
        for pending in db.scalars(select(Application).where(Application.boss_card_id==card.id,Application.id!=row.id,Application.status=='pending').with_for_update()):
            pending.status='rejected';pending.active_key=None
            notify_application(db,pending,'rejected','applicant')
        notify_application(db,row,'claimed','owner')
        audit(db,request,'boss_claimed',f'boss:{card.id}',f'application:{row.id}')
        return {'id':row.id,'status':'accepted','claimed':True}
    audit(db,request,'application_created',f'application:{row.id}')
    return {'id':row.id,'status':'pending'}

@app.get('/api/applications/{app_id}')
def application_detail(app_id:int,request:Request,db=Depends(get_db)):
    return app_dict(request,db,get_application(db,app_id))

@app.post('/api/applications/{app_id}/{action}')
def handle_application(app_id:int,action:Literal['accept','reject','cancel'],request:Request,db=Depends(get_db)):
    initial=get_application(db,app_id)
    offered=get_card(db,'team',initial.offered_team_id,True) if initial.card_type=='boss' and action=='accept' else None
    card=app_card(db,initial,True)
    row=get_application(db,app_id,True)
    side=app_side(request,db,row)
    if row.status!='pending' or row.expires_at<=now(): fail('APPLICATION_EXPIRED','申请已处理或已过期',409)
    if action in ('accept','reject') and side!='owner': fail('FORBIDDEN','只有发布者可以处理申请',403)
    if action=='cancel' and side!='applicant': fail('FORBIDDEN','只有申请者可以撤回',403)
    if action=='accept':
        if row.card_type=='boss':ensure_boss_claimable(db,card)
        else:ensure_active(card)
        team=card if row.card_type=='team' else get_card(db,'team',row.offered_team_id)
        ensure_active(team)
        row.status='accepted'
        if row.card_type=='boss':card.status='matched';card.version+=1
        db.add(Match(application_id=row.id,team_id=team.id,planned_start_at=row.requested_start_at,
            expected_end_at=row.requested_start_at+timedelta(hours=row.duration_hours) if row.requested_start_at else None))
    else:
        row.status='rejected' if action=='reject' else 'cancelled'; row.active_key=None
    notify_application(db,row,row.status,'owner' if action=='cancel' else 'applicant')
    audit(db,request,'application_'+action,f'application:{row.id}')
    db.flush()
    return app_dict(request,db,row)

@app.post('/api/matches/{match_id}/{action}')
def match_action(match_id:int,action:Literal['board','complete','cancel','dispute'],request:Request,db=Depends(get_db)):
    match=update_match(db,match_id,action,request)
    audit(db,request,'match_'+action,f'match:{match.id}')
    db.flush()
    return {'id':match.id,'status':match.status,'owner_complete':match.owner_complete,'applicant_complete':match.applicant_complete}

@app.post('/api/reviews')
def review(data:ReviewInput,request:Request,match_id:int,db=Depends(get_db)):
    match=db.scalar(select(Match).where(Match.id==match_id).with_for_update())
    if not match or match.status!='completed': fail('NOT_COMPLETED','双方确认完成后才可以评价',409)
    application=get_application(db,match.application_id); side=app_side(request,db,application)
    if application.source=='screenshot': fail('NO_VERIFIED_PEER','现场录入的成员没有网站申请记录，暂不支持评价',409)
    card=app_card(db,application)
    if application.applicant_id and application.applicant_id==card.owner_id: fail('SELF_REVIEW','不能评价自己')
    if db.scalar(select(Review.id).where(Review.match_id==match_id,Review.author_side==side)): fail('ALREADY_REVIEWED','你已评价过此次撮合',409)
    target=card.owner_id if side=='applicant' else application.applicant_id
    row=Review(match_id=match_id,author_side=side,target_user_id=target,tags='|'.join(sorted(set(data.tags))),body=data.body)
    db.add(row); db.flush(); return {'id':row.id,'status':'pending'}

@app.post('/api/reports')
def report(data:ReportInput,request:Request,db=Depends(get_db)):
    verify_challenge(db,data.challenge_id,data.answer)
    row=Report(resource=data.resource,resource_id=data.resource_id,reason=data.reason,reporter_hash=digest(actor(request,db)))
    db.add(row); db.flush(); return {'id':row.id,'status':'pending'}

@app.delete('/api/contacts/{resource}/{resource_id}')
def delete_contact(resource:Literal['team','boss','application'],resource_id:int,request:Request,db=Depends(get_db)):
    if resource=='application': require_owner(request,db,get_application(db,resource_id),'applicant_id')
    else: require_owner(request,db,get_card(db,resource,resource_id))
    row=db.scalar(select(Contact).where(Contact.resource==resource,Contact.resource_id==resource_id).with_for_update())
    if row: row.encrypted=''; row.deleted_at=now()
    if resource=='team':delete_recruitment_contact(db,get_card(db,'team',resource_id))
    audit(db,request,'contact_deleted',f'{resource}:{resource_id}')
    return {'ok':True}

@app.post('/api/ocr/character')
async def ocr(request:Request,file:UploadFile=File(...),regions:str|None=Form(None)):
    try:
        if regions and len(regions)>1000: raise ValueError()
        selected_regions=validate_regions(json.loads(regions) if regions else None)
    except (ValueError,TypeError): fail('INVALID_REGIONS','请重新框选角色能力和小地图地址',400)
    raw=await file.read(5*1024*1024+1)
    if len(raw)>5*1024*1024: fail('FILE_TOO_LARGE','图片不能超过 5 MB',413)
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('PNG','JPEG','WEBP') or image.width*image.height>12000000: raise ValueError()
            image.verify()
    except Exception: fail('INVALID_IMAGE','请选择不超过 1200 万像素的 PNG/JPEG/WebP 图片')
    try:
        async with httpx.AsyncClient(timeout=22) as client:
            result=await client.post(settings.ocr_url+'/recognize',content=raw,headers={'X-OCR-Secret':settings.ocr_secret,'Content-Type':'application/octet-stream',**({'X-OCR-Regions':json.dumps(selected_regions)} if selected_regions else {})})
        if result.status_code!=200:
            return JSONResponse({'error':{'code':'OCR_UNAVAILABLE','message':'识别暂不可用，请手动填写游戏 ID 和等级'}},status_code=503)
        return result.json()
    except httpx.HTTPError:
        fail('OCR_UNAVAILABLE','识别暂不可用，请手动填写游戏 ID 和等级',503)

@app.get('/api/admin/overview')
def admin_overview(request:Request,db=Depends(get_db)):
    admin(request,db)
    def rows(model): return db.scalars(select(model).order_by(model.id.desc()).limit(100)).all()
    users=rows(User)
    proof_users=set(db.scalars(select(RegistrationProof.user_id).where(RegistrationProof.user_id.in_([u.id for u in users]))))
    return {'reports':[{'id':r.id,'resource':r.resource,'resource_id':r.resource_id,'reason':r.reason,'status':r.status,'decision':r.decision,'created_at':iso(r.created_at)} for r in rows(Report)],
        'reviews':[{'id':r.id,'match_id':r.match_id,'tags':r.tags,'body':r.body,'status':r.status} for r in rows(Review)],
        'users':[{'id':u.id,'username':u.username,'status':u.status,'is_admin':u.is_admin,'has_registration_proof':u.id in proof_users} for u in users],
        'cards':[card_dict(c,'team') for c in rows(TeamCard)]+[card_dict(c,'boss') for c in rows(BossCard)]+[partner_dict(c) for c in rows(PartnerCard)],
        'disputes':[{'id':m.id,'application_id':m.application_id,'team_id':m.team_id} for m in db.scalars(select(Match).where(Match.status=='disputed'))],
        'audit':[{'id':r.id,'actor':r.actor,'action':r.action,'resource':r.resource,'detail':r.detail,'created_at':iso(r.created_at)} for r in rows(Audit)]}

@app.post('/api/admin/moderate')
def moderate(data:Moderation,request:Request,db=Depends(get_db)):
    user=admin(request,db)
    models={'team':TeamCard,'boss':BossCard,'partner':PartnerCard,'review':Review,'report':Report,'user':User,'match':Match}
    obj=db.scalar(select(models[data.resource]).where(models[data.resource].id==data.resource_id).with_for_update())
    if not obj: fail('NOT_FOUND','记录不存在',404)
    if data.resource in ('team','boss','partner') and data.action=='hide':
        obj.status='hidden'; obj.version+=1
        if data.resource=='team':close_recruitment(db,obj,'hidden')
    elif data.resource=='review' and data.action in ('approve','reject','hide'):
        obj.status={'approve':'approved','reject':'rejected','hide':'hidden'}[data.action]
    elif data.resource=='report' and data.action in ('resolve','reject'):
        obj.status='resolved' if data.action=='resolve' else 'rejected'; obj.decision=data.reason
    elif data.resource=='user' and data.action in ('ban','unban'):
        if obj.is_admin: fail('ADMIN_PROTECTED','管理员账号不能在此封禁',409)
        obj.status='banned' if data.action=='ban' else 'active'
        if data.action=='ban':
            for cls in (TeamCard,BossCard,PartnerCard):
                for c in db.scalars(select(cls).where(cls.owner_id==obj.id,cls.status=='active')): c.status='hidden'; c.version+=1
    elif data.resource=='match' and data.action=='cancel':
        # Re-acquire locks in canonical order rather than holding match before team.
        db.rollback()
        initial=db.get(Match,data.resource_id)
        team=get_card(db,'team',initial.team_id,True)
        application=get_application(db,initial.application_id,True)
        obj=db.scalar(select(Match).where(Match.id==data.resource_id).with_for_update().execution_options(populate_existing=True))
        if obj.status not in ('disputed','boarded','contacted'): fail('INVALID_STATE','撮合已结束',409)
        if obj.boarded_at: team.confirmed_boss_count-=1; team.version+=1
        obj.status='cancelled'; obj.finished_at=now(); application.active_key=None
    else: fail('INVALID_ACTION','不支持的审核操作')
    audit(db,request,'admin_'+data.action,f'{data.resource}:{data.resource_id}',data.reason)
    return {'ok':True}

@app.get('/api/admin/openapi')
def openapi(request:Request,db=Depends(get_db)):
    admin(request,db); return app.openapi()

from .recovery import router as recovery_router
app.include_router(recovery_router,prefix='/api')
from .partners import router as partners_router,partner_dict
app.include_router(partners_router,prefix='/api')
from .notifications import router as notifications_router
app.include_router(notifications_router,prefix='/api')
from .profiles import router as profiles_router
app.include_router(profiles_router,prefix='/api')
from .captain import router as captain_router
app.include_router(captain_router,prefix='/api')

from .party_import import router as party_import_router
app.include_router(party_import_router,prefix='/api')
