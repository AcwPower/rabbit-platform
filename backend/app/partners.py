from datetime import timedelta
from typing import Literal
from fastapi import APIRouter,Depends,Request,Query
from sqlalchemy import select,func,or_
from .db import get_db,now
from .models import PartnerCard,PartnerApplication,User,Contact,TeamCard
from .schemas import PartnerInput,PartnerApplyInput,PartnerJoinInput,Action
from .security import current_user,verify_challenge,fail,digest,save_contact,read_contact,audit
from .services import iso,card_state,ensure_active
from .profiles import account_contact
from .config import settings

def require_feature():
    if not settings.teammate_recruitment_enabled:fail('FEATURE_UNAVAILABLE','队友招募暂未开放',404)

router=APIRouter(prefix='/partners',dependencies=[Depends(require_feature)])

def get_partner(db,card_id,lock=False):
    query=select(PartnerCard).where(PartnerCard.id==card_id)
    row=db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if not row:fail('NOT_FOUND','找队友卡片不存在',404)
    return row

def owner(request,db,card):
    user=current_user(request,db,True)
    if card.owner_id!=user.id:fail('FORBIDDEN','没有此卡片的管理权限',403)
    return user

def partner_dict(card):
    fields=('id','kind','role','target_role','target_job','game_id','level','job','map_name','flower','hourly_rate','price_currency','level_min','level_max','start_time','end_time','notes','version')
    return {**{key:getattr(card,key) for key in fields},'type':'partner','status':card_state(card),
        'created_at':iso(card.created_at),'expires_at':iso(card.expires_at)}

def request_dict(db,row,user):
    card=get_partner(db,row.card_id)
    side='owner' if user.id==card.owner_id else 'applicant' if user.id==row.applicant_id else None
    if not side:fail('FORBIDDEN','没有此组队意向的查看权限',403)
    result={key:getattr(row,key) for key in ('id','role','game_id','level','job','flower','notes')}
    captain_side='owner' if card.kind=='recruit' else 'applicant'
    participants_active=all(db.get(User,uid).status=='active' for uid in (card.owner_id,row.applicant_id))
    result.update(type='partner_application',status='expired' if row.status=='pending' and row.expires_at<=now() else row.status,
        side=side,captain_side=captain_side,is_captain=side==captain_side,joined_at=iso(row.joined_at),
        can_confirm_join=side==captain_side and row.status=='accepted' and card.status in ('active','matched') and card.expires_at>now() and participants_active,
        card=partner_dict(card),created_at=iso(row.created_at),expires_at=iso(row.expires_at),contacts=None)
    if row.status in ('accepted','joined') and card.status!='hidden' and participants_active:
        result['contacts']={'publisher':read_contact(db,'partner',card.id),'applicant':read_contact(db,'partner_app',row.id)}
    return result

@router.get('/cards')
def list_partners(q:str=Query('',max_length=80),kind:Literal['recruit','job']|None=None,
        target_role:Literal['fighter','priest']|None=None,role:Literal['fighter','priest']|None=None,
        flower:Literal['active','afk','any']|None=None,level:int|None=Query(None,ge=1,le=300),
        at_time:str=Query('',max_length=5,pattern=r'^(?:|(?:[01]\d|2[0-3]):[0-5]\d)$'),
        page:int=Query(1,ge=1),db=Depends(get_db)):
    conditions=[PartnerCard.status=='active',PartnerCard.expires_at>now(),User.status=='active']
    if q:conditions.append(or_(PartnerCard.map_name.contains(q,autoescape=True),PartnerCard.game_id.contains(q,autoescape=True),PartnerCard.job.contains(q,autoescape=True),PartnerCard.target_job.contains(q,autoescape=True)))
    if role:conditions.append(PartnerCard.role==role)
    if kind:conditions.append(PartnerCard.kind==kind)
    if target_role:conditions.append(PartnerCard.target_role==target_role)
    if flower:conditions.append(PartnerCard.flower==flower)
    if level:conditions.extend([PartnerCard.level_min<=level,PartnerCard.level_max>=level])
    if at_time:
        c=PartnerCard
        conditions.append(or_((c.start_time<c.end_time)&(c.start_time<=at_time)&(c.end_time>=at_time),
            (c.start_time>=c.end_time)&or_(c.start_time<=at_time,c.end_time>=at_time)))
    query=select(PartnerCard).join(User,User.id==PartnerCard.owner_id).where(*conditions)
    total=db.scalar(select(func.count()).select_from(query.subquery()))
    rows=db.scalars(query.order_by(PartnerCard.created_at.desc(),PartnerCard.id.desc()).offset((page-1)*20).limit(20))
    return {'items':[partner_dict(c) for c in rows],'total':total,'page':page,'has_more':page*20<total}

@router.get('/me')
def my_partners(request:Request,db=Depends(get_db)):
    user=current_user(request,db,True)
    cards=db.scalars(select(PartnerCard).where(PartnerCard.owner_id==user.id).order_by(PartnerCard.created_at.desc()).limit(100)).all()
    incoming=db.scalars(select(PartnerApplication).join(PartnerCard).where(PartnerCard.owner_id==user.id).order_by(PartnerApplication.created_at.desc()).limit(100))
    outgoing=db.scalars(select(PartnerApplication).where(PartnerApplication.applicant_id==user.id).order_by(PartnerApplication.created_at.desc()).limit(100))
    return {'cards':[partner_dict(c) for c in cards],'incoming':[request_dict(db,r,user) for r in incoming],
        'outgoing':[request_dict(db,r,user) for r in outgoing]}

@router.get('/cards/{card_id}')
def partner_detail(card_id:int,request:Request,db=Depends(get_db)):
    card=get_partner(db,card_id);user=current_user(request,db)
    own=bool(user and user.id==card.owner_id)
    publisher=db.get(User,card.owner_id)
    if (card.status=='hidden' or publisher.status!='active') and not own:fail('NOT_FOUND','此卡片已被隐藏',404)
    result=partner_dict(card)
    result.update(is_owner=own,public_contact=read_contact(db,'partner',card.id,True),
        publisher={'id':publisher.id,'name':publisher.username,'registered_at':iso(publisher.created_at)})
    if own:
        result['contact']=read_contact(db,'partner',card.id)
        result['applications']=[request_dict(db,r,user) for r in db.scalars(select(PartnerApplication).where(PartnerApplication.card_id==card.id).order_by(PartnerApplication.created_at.desc()).limit(100))]
    return result

def write_partner(data,request,db,card=None):
    user=current_user(request,db,True)
    if card:
        owner(request,db,card);ensure_active(card)
        if data.version!=card.version:fail('VERSION_CONFLICT','卡片刚刚被更新，请刷新后编辑',409)
        if (data.kind,data.role,data.target_role,data.target_job)!=(card.kind,card.role,card.target_role,card.target_job):fail('ROLE_LOCKED','发布后不能更换卡片类型、身份或目标职业，请下架后重新发布',409)
    else:
        verify_challenge(db,data.challenge_id,data.answer)
        db.execute(select(User.id).where(User.id==user.id).with_for_update())
        count=db.scalar(select(func.count(PartnerCard.id)).where(PartnerCard.owner_id==user.id,PartnerCard.status=='active',PartnerCard.expires_at>now()))
        if count>=5:fail('LIMIT_REACHED','最多同时发布 5 张找队友卡片')
        card=PartnerCard(owner_id=user.id,expires_at=now()+timedelta(hours=data.duration_hours));db.add(card)
    for key in ('kind','role','target_role','target_job','game_id','level','job','map_name','flower','hourly_rate','price_currency','level_min','level_max','start_time','end_time','notes'):
        setattr(card,key,getattr(data,key))
    if card.id:card.version+=1
    db.flush();save_contact(db,'partner',card.id,account_contact(db,request,user,data.contact),data.public_contact,card.expires_at+timedelta(days=7))
    audit(db,request,'partner_saved',f'partner:{card.id}')
    return partner_dict(card)

@router.post('/cards',status_code=201)
def create_partner(data:PartnerInput,request:Request,db=Depends(get_db)):return write_partner(data,request,db)

@router.put('/cards/{card_id}')
def edit_partner(card_id:int,data:PartnerInput,request:Request,db=Depends(get_db)):
    return write_partner(data,request,db,get_partner(db,card_id,True))

@router.post('/cards/{card_id}/status')
def partner_status(card_id:int,data:Action,request:Request,db=Depends(get_db)):
    card=get_partner(db,card_id,True);owner(request,db,card);ensure_active(card)
    if data.action not in ('close','matched'):fail('INVALID_ACTION','不支持的操作')
    card.status='matched' if data.action=='matched' else 'closed';card.version+=1
    for row in db.scalars(select(PartnerApplication).where(PartnerApplication.card_id==card.id,PartnerApplication.status=='pending').with_for_update()):
        row.status='cancelled';row.active_key=None
    audit(db,request,'partner_'+card.status,f'partner:{card.id}')
    return {'ok':True}

def check_fit(card,data):
    expected=card.target_role
    if card.kind=='recruit' and data.role!=expected:fail('ROLE_MISMATCH','对方正在寻找祭司' if expected=='priest' else '对方正在寻找打手',409)
    if card.target_job=='龙骑士' and data.job not in ('龙骑','龙骑士'):fail('JOB_MISMATCH','对方正在招募龙骑士，请使用相应职业的角色申请',409)
    if not card.level_min<=data.level<=card.level_max:fail('LEVEL_MISMATCH','角色等级不在对方要求范围内',409)
    if card.kind=='recruit' and expected=='priest' and card.flower!='any' and card.flower!=data.flower:fail('FLOWER_MISMATCH','花类型不符合对方要求',409)

@router.post('/applications',status_code=201)
def contact_partner(data:PartnerApplyInput,request:Request,db=Depends(get_db)):
    user=current_user(request,db,True);card=get_partner(db,data.card_id,True);ensure_active(card)
    if card.owner_id==user.id:fail('SELF_APPLY','不能联系自己发布的卡片',409)
    check_fit(card,data);verify_challenge(db,data.challenge_id,data.answer)
    key=digest(f'partner:{card.id}:{user.id}')
    old=db.scalar(select(PartnerApplication).where(PartnerApplication.active_key==key))
    if old and old.status=='pending' and old.expires_at<=now():old.active_key=None;old.status='expired';db.flush()
    elif old:fail('DUPLICATE_APPLICATION','已经联系过对方，请查看已发意向',409)
    row=PartnerApplication(card_id=card.id,applicant_id=user.id,active_key=key,
        **data.model_dump(include={'role','game_id','level','job','flower','notes'}),expires_at=min(card.expires_at,now()+timedelta(hours=24)))
    db.add(row);db.flush();save_contact(db,'partner_app',row.id,account_contact(db,request,user,data.contact),expires=card.expires_at+timedelta(days=7))
    audit(db,request,'partner_application',f'partner_app:{row.id}')
    return {'id':row.id,'status':'pending','type':'partner_application'}

@router.get('/applications/{app_id}')
def partner_application(app_id:int,request:Request,db=Depends(get_db)):
    user=current_user(request,db,True);row=db.get(PartnerApplication,app_id)
    if not row:fail('NOT_FOUND','组队意向不存在',404)
    return request_dict(db,row,user)

@router.post('/applications/{app_id}/{action}')
def handle_partner_application(app_id:int,action:Literal['accept','reject','cancel','join'],request:Request,data:PartnerJoinInput|None=None,db=Depends(get_db)):
    user=current_user(request,db,True);initial=db.get(PartnerApplication,app_id)
    if not initial:fail('NOT_FOUND','组队意向不存在',404)
    card=get_partner(db,initial.card_id,True)
    row=db.scalar(select(PartnerApplication).where(PartnerApplication.id==app_id).with_for_update().execution_options(populate_existing=True))
    side=request_dict(db,row,user)['side']
    if action=='join':
        captain_id=card.owner_id if card.kind=='recruit' else row.applicant_id
        if user.id!=captain_id:fail('CAPTAIN_REQUIRED','只有队长可以确认入队',403)
        if row.status!='accepted':fail('INVALID_STATE','先同意意向并交换微信，再确认入队',409)
        if card.status not in ('active','matched') or card.expires_at<=now():fail('CARD_UNAVAILABLE','招募已结束或过期，不能确认入队',409)
        if not all(db.get(User,uid).status=='active' for uid in (card.owner_id,row.applicant_id)):fail('ACCOUNT_BANNED','对方账号已停用',409)
        if not data or data.wechat_confirmed is not True:fail('WECHAT_CONFIRMATION_REQUIRED','请先确认已添加微信并谈妥组队安排',422)
        linked_team=db.scalar(select(TeamCard).where(TeamCard.teammate_recruitment_id==card.id))
        if linked_team:
            if linked_team.status!='active' or linked_team.expires_at<=now():fail('CARD_UNAVAILABLE','关联的老板招募已经结束',409)
            if db.scalar(select(PartnerApplication.id).where(PartnerApplication.card_id==card.id,PartnerApplication.status=='joined')):
                fail('TEAMMATE_FILLED','这张招募已确认一位队友入队',409)
            card.status='matched';card.version+=1
            for other in db.scalars(select(PartnerApplication).where(PartnerApplication.card_id==card.id,PartnerApplication.status=='pending').with_for_update()):
                other.status='cancelled';other.active_key=None
        row.status='joined';row.joined_at=now()
    elif action=='cancel' and row.status in ('accepted','joined'):row.status='cancelled';row.active_key=None
    else:
        if row.status!='pending' or row.expires_at<=now():fail('APPLICATION_EXPIRED','此意向已处理或已过期',409)
        if action in ('accept','reject') and side!='owner':fail('FORBIDDEN','只有发布者可处理意向',403)
        if action=='cancel' and side!='applicant':fail('FORBIDDEN','只有申请者可撤回意向',403)
        if action=='accept':
            ensure_active(card);check_fit(card,row)
            if db.get(User,row.applicant_id).status!='active':fail('ACCOUNT_BANNED','对方账号已停用',409)
            row.status='accepted'
        else:row.status='rejected' if action=='reject' else 'cancelled';row.active_key=None
    audit(db,request,'partner_'+action,f'partner_app:{row.id}')
    db.flush();return request_dict(db,row,user)

@router.delete('/contacts/{resource}/{resource_id}')
def delete_partner_contact(resource:Literal['partner','partner_app'],resource_id:int,request:Request,db=Depends(get_db)):
    user=current_user(request,db,True)
    if resource=='partner':owner(request,db,get_partner(db,resource_id))
    else:
        row=db.get(PartnerApplication,resource_id)
        if not row or row.applicant_id!=user.id:fail('FORBIDDEN','没有此联系方式的管理权限',403)
    contact=db.scalar(select(Contact).where(Contact.resource==resource,Contact.resource_id==resource_id).with_for_update())
    if contact:contact.encrypted='';contact.deleted_at=now()
    audit(db,request,'contact_deleted',f'{resource}:{resource_id}')
    return {'ok':True}
