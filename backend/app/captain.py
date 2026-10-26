from datetime import timedelta, timezone
from fastapi import APIRouter, Depends, Request
from pydantic import AwareDatetime, Field
from sqlalchemy import select, or_, and_
from .db import get_db,now
from .models import TeamCard,BossCard,Application,Match,ApplicationNotification
from .schemas import Input
from .security import current_user,owns,fail,audit
from .services import card_dict,iso,get_card,get_application,app_dict
from .application_events import notify_application
from .notifications import NotificationQuery,scopes

router=APIRouter()


@router.post('/boss/bookings/query')
def boss_bookings(data:NotificationQuery,request:Request,db=Depends(get_db)):
    _,_,_,owner,applicant=scopes(request,db,data.managed)
    # The boss is the applicant on a team card, or the owner of a boss card.
    allowed=or_(and_(Application.card_type=='team',applicant),and_(Application.card_type=='boss',owner))
    base=select(Application,Match).outerjoin(Match,Match.application_id==Application.id).where(allowed)
    active=or_(Match.status.in_(['contacted','boarded','disputed']),and_(Match.id.is_(None),Application.status=='pending',Application.expires_at>now()))
    current=db.execute(base.where(active).order_by(Application.created_at.desc()).limit(100)).all()
    current_ids=[a.id for a,m in current]
    ended=or_(Match.status.in_(['completed','cancelled']),and_(Match.id.is_(None),or_(Application.status!='pending',Application.expires_at<=now())))
    past=db.execute(base.where(ended).order_by(Application.created_at.desc()).limit(20)).all()
    result=[]
    for row,match in current+past:
        team=get_card(db,'team',row.team_card_id or row.offered_team_id)
        boss=db.get(BossCard,row.boss_card_id) if row.card_type=='boss' else None
        status=match.status if match else ('expired' if row.status=='pending' and row.expires_at<=now() else row.status)
        start=match.planned_start_at if match and match.planned_start_at else row.requested_start_at
        end=match.expected_end_at if match else None
        if not end and start and row.duration_hours:end=start+timedelta(hours=row.duration_hours)
        result.append({'application_id':row.id,'game_id':boss.game_id if boss else row.game_id,
            'map_name':team.map_name,'captain_name':team.game_id,'status':status,'current':row.id in current_ids,
            'planned_start_at':iso(start),'expected_end_at':iso(end),
            'boarded_at':iso(match.boarded_at) if match else None,'finished_at':iso(match.finished_at) if match else None,
            'access':{'type':'boss','id':boss.id} if boss else {'type':'application','id':row.id}})
    return {'bookings':result,'server_time':iso(now())}

class ScheduleInput(Input):
    planned_start_at: AwareDatetime
    expected_end_at: AwareDatetime
    version: int = Field(ge=1)


@router.get('/captain/teams')
def captain_teams(request:Request,db=Depends(get_db)):
    user=current_user(request,db,True)
    ongoing=select(Match.team_id).where(Match.status.in_(['contacted','boarded','disputed']))
    current=db.scalars(select(TeamCard).where(TeamCard.owner_id==user.id,
        or_(TeamCard.status=='active',TeamCard.id.in_(ongoing))).order_by(TeamCard.created_at.desc())).all()
    ids=[t.id for t in current]
    history=db.scalars(select(TeamCard).where(TeamCard.owner_id==user.id,TeamCard.id.not_in(ids)).order_by(TeamCard.created_at.desc()).limit(20)).all()
    teams=current+history;ids=[t.id for t in teams]
    applications=db.scalars(select(Application).where(or_(Application.team_card_id.in_(ids),Application.offered_team_id.in_(ids))).order_by(Application.created_at.desc())).all()
    matches={m.application_id:m for m in db.scalars(select(Match).where(Match.team_id.in_(ids)))}
    boss_ids=[a.boss_card_id for a in applications if a.boss_card_id]
    bosses={b.id:b for b in db.scalars(select(BossCard).where(BossCard.id.in_(boss_ids)))}
    grouped={t.id:[] for t in teams}
    for row in applications:
        team_id=row.team_card_id if row.card_type=='team' else row.offered_team_id
        match=matches.get(row.id)
        status=match.status if match else ('expired' if row.status=='pending' and row.expires_at<=now() else row.status)
        boss=bosses.get(row.boss_card_id)
        grouped[team_id].append({'application_id':row.id,'side':'owner' if row.card_type=='team' else 'applicant',
            'game_id':row.game_id if row.card_type=='team' else boss.game_id,'level':row.level if row.card_type=='team' else boss.level,
            'status':status,'source':row.source,'created_at':iso(row.created_at),'notes':boss.notes if boss else row.notes,
            'requested_start_at':iso(row.requested_start_at),'duration_hours':row.duration_hours,
            'match':{'id':match.id,'boarded_at':iso(match.boarded_at),'planned_start_at':iso(match.planned_start_at),'expected_end_at':iso(match.expected_end_at),
                     'finished_at':iso(match.finished_at),'schedule_version':match.schedule_version,'reminder_ignored':match.reminder_ignored_version==match.schedule_version} if match else None})
    result=[]
    for team in teams:
        members=grouped[team.id]
        active=[m for m in members if m['status'] in ('pending','contacted','boarded','disputed')]
        past=[m for m in members if m not in active][:20]
        card=card_dict(team,'team')
        result.append({'card':card,'current':card['status'] in ('active','full') or bool(active),'members':active+past})
    return {'teams':result,'server_time':iso(now())}


@router.put('/matches/{match_id}/schedule')
def change_schedule(match_id:int,data:ScheduleInput,request:Request,db=Depends(get_db)):
    current_user(request,db,True)
    initial=db.get(Match,match_id)
    if not initial:fail('NOT_FOUND','撮合记录不存在',404)
    team=get_card(db,'team',initial.team_id,True)
    row=get_application(db,initial.application_id,True)
    match=db.scalar(select(Match).where(Match.id==match_id).with_for_update().execution_options(populate_existing=True))
    if not owns(request,db,team):fail('FORBIDDEN','只有这支队伍的打手队长可以调整上车时段',403)
    if match.status not in ('contacted','boarded','disputed'):fail('INVALID_STATE','只有已同意或正在挂机的老板可以调整时段',409)
    if data.version!=match.schedule_version:fail('VERSION_CONFLICT','时间刚刚被修改，请刷新后重试',409)
    end=data.expected_end_at.astimezone(timezone.utc).replace(tzinfo=None,microsecond=0)
    start=data.planned_start_at.astimezone(timezone.utc).replace(tzinfo=None,microsecond=0)
    if end<=start or end>start+timedelta(days=7) or (match.boarded_at and end<=match.boarded_at):fail('INVALID_END_TIME','结束时间须晚于开始和实际上车时间，单次时段不超过 7 天',422)
    if start>now()+timedelta(days=7):fail('INVALID_START_TIME','预计上车时间不能超过未来 7 天',422)
    if start!=match.planned_start_at or end!=match.expected_end_at:
        before=f'{iso(match.planned_start_at)} — {iso(match.expected_end_at)}';match.planned_start_at=start;match.expected_end_at=end;match.schedule_version+=1
        notify_application(db,row,f'end:{match.schedule_version}','applicant' if row.card_type=='team' else 'owner')
        audit(db,request,'match_schedule_changed',f'match:{match.id}',f'{before} -> {iso(start)} — {iso(end)}')
    db.flush()
    return app_dict(request,db,row)


class IgnoreReminderInput(Input):
    version: int = Field(ge=1)


@router.post('/matches/{match_id}/reminders/ignore')
def ignore_reminder(match_id:int,data:IgnoreReminderInput,request:Request,db=Depends(get_db)):
    current_user(request,db,True)
    initial=db.get(Match,match_id)
    if not initial:fail('NOT_FOUND','撮合记录不存在',404)
    team=get_card(db,'team',initial.team_id,True)
    row=get_application(db,initial.application_id,True)
    match=db.scalar(select(Match).where(Match.id==match_id).with_for_update().execution_options(populate_existing=True))
    if not owns(request,db,team):fail('FORBIDDEN','只有该队伍的打手可以忽略提醒',403)
    if match.status not in ('boarded','disputed'):fail('INVALID_STATE','只有正在挂机的老板可以忽略提醒',409)
    if data.version!=match.schedule_version:fail('VERSION_CONFLICT','时段已经调整，请刷新后重试',409)
    if match.reminder_ignored_version!=match.schedule_version:
        match.reminder_ignored_version=match.schedule_version
        audit(db,request,'booking_reminder_ignored',f'match:{match.id}',f'schedule_version:{match.schedule_version}')
    recipient='owner' if row.card_type=='team' else 'applicant'
    for event in db.scalars(select(ApplicationNotification).where(ApplicationNotification.application_id==row.id,
            ApplicationNotification.recipient_side==recipient,ApplicationNotification.event.in_([f'due:{match.schedule_version}',f'late:{match.schedule_version}']),ApplicationNotification.read_at.is_(None))):
        event.read_at=now()
    db.flush()
    return app_dict(request,db,row)
