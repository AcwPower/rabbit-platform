from datetime import timedelta
from sqlalchemy import select, func
from .db import now
from .models import TeamCard, BossCard, Application, Match, User, Review, Contact, PartnerCard
from .security import fail, owns, read_contact
from .application_events import notify_application
from .schedule import default_end_at

def card_class(kind):
    if kind not in ('team','boss'):
        fail('NOT_FOUND', '记录不存在', 404)
    return TeamCard if kind == 'team' else BossCard

def get_card(db, kind, card_id, lock=False):
    model = card_class(kind)
    query = select(model).where(model.id == card_id)
    card = db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if not card:
        fail('NOT_FOUND', '卡片不存在', 404)
    return card

def card_state(card):
    if card.status != 'active': return card.status
    if card.expires_at <= now(): return 'expired'
    if isinstance(card, TeamCard) and remaining(card) == 0: return 'full'
    return 'active'

def remaining(card):
    return max(0,card.capacity - card.fighter_count - card.priest_count - int(card.teammate_need!='none') - card.confirmed_boss_count)

def ensure_active(card):
    state = card_state(card)
    if state != 'active':
        fail('CARD_UNAVAILABLE', '卡片已满员、过期或下架', 409)

def ensure_boss_claimable(db, card):
    # The caller holds the boss-card row lock. This also protects legacy matches
    # created before first-come claims were introduced.
    existing=db.scalar(select(Match.id).join(Application,Application.id==Match.application_id).where(
        Application.boss_card_id==card.id,Match.status.in_(['contacted','boarded','disputed'])).limit(1))
    if card.status=='matched' or existing:
        fail('BOSS_CLAIMED','这位老板已被其他打手认领，请选择其他老板',409)
    ensure_active(card)

def iso(value):
    return value.isoformat()+'Z' if value else None

def card_dict(card, kind, db=None, detail=False):
    fields = ['id','game_id','level','map_name','capacity','flower','price_mode','price_currency','price',
              'night_price','exp_min','exp_max','start_time','end_time','notes','version']
    result = {key:getattr(card,key) for key in fields}
    result.update(type=kind,status=card_state(card),created_at=iso(card.created_at),expires_at=iso(card.expires_at))
    if kind == 'team':
        for key in ['fighter_count','priest_count','confirmed_boss_count','level_min','level_max','teammate_need','teammate_recruitment_id']:
            result[key] = getattr(card,key)
        result['remaining'] = remaining(card)
        result['boss_slots'] = card.capacity-card.fighter_count-card.priest_count-int(card.teammate_need!='none')
        if db and card.teammate_need!='none' and card.teammate_recruitment_id:
            linked=db.get(PartnerCard,card.teammate_recruitment_id)
            if linked:result.update(teammate_level_min=linked.level_min,teammate_level_max=linked.level_max)
    if detail and db:
        user = db.get(User,card.owner_id) if card.owner_id else None
        result['publisher'] = {'id':user.id,'name':user.username,'registered_at':iso(user.created_at)} if user else None
        result['public_contact'] = read_contact(db,kind,card.id,True) if kind=='team' else None
        result['reviews'] = []
        result['completed_count'] = 0
        if user:
            result['completed_count'] = db.scalar(select(func.count(Match.id)).join(TeamCard,Match.team_id==TeamCard.id).where(TeamCard.owner_id==user.id,Match.status=='completed')) or 0
            reviews = db.scalars(select(Review).where(Review.target_user_id==user.id,Review.status=='approved').order_by(Review.created_at.desc()).limit(8)).all()
            result['reviews'] = [{'id':r.id,'tags':r.tags.split('|'),'body':r.body,'created_at':iso(r.created_at)} for r in reviews]
    return result

def app_card(db, application, lock=False):
    return get_card(db, application.card_type, application.team_card_id or application.boss_card_id, lock)

def app_side(request,db,application):
    card = app_card(db,application)
    if owns(request,db,card): return 'owner'
    if owns(request,db,application,'applicant_id'): return 'applicant'
    fail('FORBIDDEN','没有此申请的查看权限',403)

def get_application(db, app_id, lock=False):
    query=select(Application).where(Application.id==app_id)
    row=db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
    if not row: fail('NOT_FOUND','申请不存在',404)
    return row

def app_dict(request,db,row):
    side=app_side(request,db,row)
    card=app_card(db,row)
    match=db.scalar(select(Match).where(Match.application_id==row.id))
    result={'id':row.id,'card_type':row.card_type,'card_id':card.id,'game_id':row.game_id,
        'level':row.level,'source':row.source,'notes':row.notes,'status':'expired' if row.status=='pending' and row.expires_at<=now() else row.status,
        'created_at':iso(row.created_at),'expires_at':iso(row.expires_at),'side':side,'card':card_dict(card,row.card_type),
        'requested_start_at':iso(row.requested_start_at),'duration_hours':row.duration_hours,
        'match':None,'contacts':None}
    if row.offered_team_id:
        result['offered_team']=card_dict(get_card(db,'team',row.offered_team_id),'team')
    if match:
        team=get_card(db,'team',match.team_id)
        result['match']={'id':match.id,'status':match.status,'owner_complete':match.owner_complete,
            'applicant_complete':match.applicant_complete,'can_board':owns(request,db,team),
            'boarded_at':iso(match.boarded_at),'planned_start_at':iso(match.planned_start_at),'expected_end_at':iso(match.expected_end_at),
            'finished_at':iso(match.finished_at),'schedule_version':match.schedule_version,
            'reminder_ignored':match.reminder_ignored_version==match.schedule_version,
            'can_complete':owns(request,db,team),
            'reviewed':bool(db.scalar(select(Review.id).where(Review.match_id==match.id,Review.author_side==side)))}
        if match.status not in ('cancelled',) and row.status=='accepted':
            result['contacts']={'publisher':read_contact(db,row.card_type,card.id),'applicant':read_contact(db,'application',row.id)}
    return result

def update_match(db, match_id, action, request):
    # Lock order: team -> boss card (when applicable) -> application -> match.
    initial=db.get(Match,match_id)
    if not initial: fail('NOT_FOUND','撮合记录不存在',404)
    team=get_card(db,'team',initial.team_id,True)
    initial_application=get_application(db,initial.application_id)
    boss=get_card(db,'boss',initial_application.boss_card_id,True) if initial_application.card_type=='boss' else None
    application=get_application(db,initial.application_id,True)
    match=db.scalar(select(Match).where(Match.id==match_id).with_for_update().execution_options(populate_existing=True))
    side=app_side(request,db,application)
    if action=='board':
        if not owns(request,db,team): fail('FORBIDDEN','由队长确认上车',403)
        if match.status!='contacted': fail('INVALID_STATE','当前状态不能上车',409)
        if match.expected_end_at and match.expected_end_at<=now():fail('SCHEDULE_ENDED','约定时段已结束，请先调整该老板的上车和结束时间',409)
        ensure_active(team)
        target=app_card(db,application)
        allowed=('active','matched') if application.card_type=='boss' else ('active',)
        if target.status not in allowed or target.expires_at<=now(): fail('CARD_UNAVAILABLE','原卡片已过期或结束',409)
        if application.card_type=='boss':
            if target.level < team.level_min or target.level > team.level_max: fail('LEVEL_MISMATCH','老板等级不在队伍范围内',409)
            if target.flower=='active' and team.flower!='active': fail('FLOWER_MISMATCH','求车要求活花',409)
        team.confirmed_boss_count+=1
        team.version+=1
        match.status='boarded'; match.boarded_at=now()
        if not match.planned_start_at:match.planned_start_at=match.boarded_at
        if not match.expected_end_at:match.expected_end_at=default_end_at(match.boarded_at,team.end_time)
    elif action=='complete':
        if not owns(request,db,team):fail('FORBIDDEN','由打手队长结束挂机，老板无需确认',403)
        if match.status!='boarded': fail('INVALID_STATE','只有已上车的撮合可确认完成',409)
        setattr(match,side+'_complete',True)
        match.status='completed'; match.finished_at=now()
        team.confirmed_boss_count-=1; team.version+=1
        application.active_key=None
    elif action=='cancel':
        if match.status not in ('contacted','boarded','disputed'): fail('INVALID_STATE','此撮合已经结束',409)
        if match.boarded_at:
            team.confirmed_boss_count-=1; team.version+=1
        match.status='cancelled'; match.finished_at=now()
        application.active_key=None
        if boss and boss.status=='matched' and boss.expires_at>now():
            db.flush()
            another=db.scalar(select(Match.id).join(Application,Application.id==Match.application_id).where(
                Application.boss_card_id==boss.id,Match.status.in_(['contacted','boarded','disputed'])).limit(1))
            if not another:boss.status='active';boss.version+=1
    elif action=='dispute':
        if match.status!='boarded': fail('INVALID_STATE','只有上车后可以标记争议',409)
        match.status='disputed'
    else: fail('INVALID_ACTION','不支持的操作')
    recipient='applicant' if side=='owner' else 'owner'
    if action=='board':recipient='applicant' if application.card_type=='team' else 'owner'
    if action!='complete' or match.status=='completed':
        notify_application(db,application,match.status,recipient)
    return match
