from datetime import timedelta
from math import ceil,floor
from typing import Literal
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select, func, or_, and_, cast, Integer
from .db import get_db, now
from .models import Application, ApplicationNotification, PartnerApplication, TeamCard, BossCard, PartnerCard, User, Match
from .security import current_user, digest
from .schemas import Input
from .services import iso
from .config import settings

router = APIRouter()

class ManagedRecord(Input):
    type: Literal['boss','application']
    id: int = Field(gt=0)
    manage: str = Field(min_length=40,max_length=128,pattern=r'^[a-zA-Z0-9_-]+$')

class NotificationQuery(Input):
    managed: list[ManagedRecord] = Field(default_factory=list,max_length=100)

class NotificationRead(NotificationQuery):
    ids: list[int] = Field(max_length=100)


def scopes(request, db, managed):
    user=current_user(request,db)
    uid=user.id if user else -1
    boss_credentials=[and_(BossCard.id==r.id,BossCard.manage_hash==digest(r.manage)) for r in managed if r.type=='boss']
    app_credentials=[and_(Application.id==r.id,Application.manage_hash==digest(r.manage)) for r in managed if r.type=='application']
    teams=select(TeamCard.id).where(TeamCard.owner_id==uid)
    bosses=select(BossCard.id).where(or_(BossCard.owner_id==uid,and_(BossCard.owner_id.is_(None),or_(False,*boss_credentials))))
    owner=or_(Application.team_card_id.in_(teams),Application.boss_card_id.in_(bosses))
    applicant=or_(Application.applicant_id==uid,and_(Application.applicant_id.is_(None),or_(False,*app_credentials)))
    return user,teams,bosses,owner,applicant


def progress_query(owner,applicant):
    at=now()
    is_reminder=or_(ApplicationNotification.event.like('due:%'),ApplicationNotification.event.like('late:%'))
    current_reminder=select(Match.id).where(Match.application_id==ApplicationNotification.application_id,
        Match.status.in_(['boarded','disputed']),or_(Match.reminder_ignored_version.is_(None),Match.reminder_ignored_version!=Match.schedule_version),
        or_(and_(ApplicationNotification.event.like('due:%'),cast(func.substr(ApplicationNotification.event,5),Integer)==Match.schedule_version,Match.expected_end_at>at,Match.expected_end_at<=at+timedelta(minutes=30)),
            and_(ApplicationNotification.event.like('late:%'),cast(func.substr(ApplicationNotification.event,6),Integer)==Match.schedule_version,Match.expected_end_at<=at))).exists()
    return select(ApplicationNotification).join(Application,Application.id==ApplicationNotification.application_id).where(
        ApplicationNotification.read_at.is_(None),ApplicationNotification.created_at>=at-timedelta(days=30),
        or_(~is_reminder,current_reminder),
        or_(and_(ApplicationNotification.recipient_side=='owner',owner),
            and_(ApplicationNotification.recipient_side=='applicant',applicant)))


def snapshot(request,db,managed):
    user,teams,bosses,owner,applicant=scopes(request,db,managed)
    at=now()
    teams=teams.where(TeamCard.status=='active',TeamCard.expires_at>at)
    bosses=bosses.where(BossCard.status=='active',BossCard.expires_at>at)
    active_users=select(User.id).where(User.status=='active')
    applications=select(Application).where(
        Application.status=='pending',Application.expires_at>at,
        or_(Application.applicant_id.is_(None),Application.applicant_id.in_(active_users)),
        or_(Application.team_card_id.in_(teams),Application.boss_card_id.in_(bosses)))
    partners=select(PartnerApplication).join(PartnerCard,PartnerCard.id==PartnerApplication.card_id).where(
        PartnerCard.owner_id==(user.id if user else -1),PartnerCard.status=='active',PartnerCard.expires_at>at,
        PartnerApplication.status=='pending',PartnerApplication.expires_at>at,PartnerApplication.applicant_id.in_(active_users))
    if not settings.teammate_recruitment_enabled:partners=partners.where(False)
    progress=progress_query(owner,applicant)
    counts={key:db.scalar(select(func.count()).select_from(query.subquery())) for key,query in
            [('applications',applications),('partners',partners),('updates',progress)]}
    latest=[]
    for query,model,kind in [(applications,Application,'application'),(partners,PartnerApplication,'partner_application')]:
        for row in db.scalars(query.order_by(model.id.desc()).limit(20)):
            if kind=='application':
                card=db.get(TeamCard if row.card_type=='team' else BossCard,row.team_card_id or row.boss_card_id)
                label='上车申请' if row.card_type=='team' else '接单意向'
                access={'type':row.card_type,'id':card.id}
            else:
                card=db.get(PartnerCard,row.card_id);label='队友申请' if card.kind=='recruit' else '入队邀请';access=None
            latest.append({'id':row.id,'kind':kind,'key':f'{kind}:{row.id}','label':label,'side':'owner','access':access,
                           'game_id':row.game_id,'map_name':card.map_name,'created_at':iso(row.created_at),'expires_at':iso(row.expires_at)})
    labels={'claimed':'你的求带需求已被打手认领','accepted':'申请已同意，可以交换微信','boarded':'队长已确认上车，老板位已保留',
            'rejected':'申请未通过','cancelled':'本次组队已取消','completed':'本次组队已完成','disputed':'本次组队已标记争议'}
    updates=[]
    for event in db.scalars(progress.order_by(ApplicationNotification.id.desc()).limit(100)):
        row=db.get(Application,event.application_id)
        card=db.get(TeamCard if row.card_type=='team' else BossCard,row.team_card_id or row.boss_card_id)
        access={'type':'application','id':row.id} if event.recipient_side=='applicant' else {'type':row.card_type,'id':card.id}
        reminder=event.event.startswith(('due:','late:'))
        extra={}
        if reminder:
            match=db.scalar(select(Match).where(Match.application_id==row.id))
            team=db.get(TeamCard,match.team_id)
            late=event.event.startswith('late:')
            minutes=max(1,(floor if late else ceil)(abs((match.expected_end_at-at).total_seconds())/60))
            label='老板已进入超时挂机' if late else '老板即将结束挂机'
            end=(match.expected_end_at+timedelta(hours=8)).strftime('%m/%d %H:%M')
            extra={'severity':'danger' if late else 'warning','match_id':match.id,'team_id':team.id,
                'expected_end_at':iso(match.expected_end_at),'schedule_version':match.schedule_version,
                'message':f'{"已超时" if late else "还剩"} {minutes} 分钟 · 预计结束 {end}（北京时间）。可继续挂机，超时费用由双方协商补齐尾款。'}
        else:
            label='上车时段已调整' if event.event.startswith('end:') else labels[event.event]
            if event.event=='claimed':extra={'message':'打手已获得你的微信，会与你联系。无需同意，沟通后由打手确认上车。'}
        kind='booking_reminder' if reminder else 'progress'
        updates.append({'id':event.id,'kind':kind,'key':f'{kind}:{event.id}','application_id':row.id,
            'label':label,'event':event.event,'side':event.recipient_side,'access':access,
            'game_id':(row.game_id if row.card_type=='team' else card.game_id) if reminder else row.game_id,
            'map_name':team.map_name if reminder else card.map_name,'created_at':iso(event.created_at),**extra})
    latest.extend(updates)
    latest.sort(key=lambda item:({'danger':2,'warning':1}.get(item.get('severity'),0),item['created_at'],item['id']),reverse=True)
    return {'total':sum(counts.values()),'counts':counts,'latest':latest,'updates':updates}


@router.get('/notifications')
def notifications(request:Request,db=Depends(get_db)):
    current_user(request,db,True)
    return snapshot(request,db,[])


@router.post('/notifications/query')
def query_notifications(data:NotificationQuery,request:Request,db=Depends(get_db)):
    return snapshot(request,db,data.managed)


@router.post('/notifications/read')
def read_notifications(data:NotificationRead,request:Request,db=Depends(get_db)):
    _,_,_,owner,applicant=scopes(request,db,data.managed)
    rows=db.scalars(progress_query(owner,applicant).where(ApplicationNotification.id.in_(data.ids))).all()
    for row in rows:row.read_at=now()
    db.flush()
    return {'read':len(rows)}
