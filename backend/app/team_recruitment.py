from datetime import timedelta
from sqlalchemy import select,func
from .models import PartnerCard,PartnerApplication,User,Contact,Character
from .db import now
from .security import fail,save_contact

def close_recruitment(db,team,status='closed'):
    if not team.teammate_recruitment_id:return
    row=db.scalar(select(PartnerCard).where(PartnerCard.id==team.teammate_recruitment_id).with_for_update())
    if not row:return
    # A parent edit must never unhide a moderated card.
    if row.status!='hidden' or status=='hidden':row.status=status;row.version+=1
    for intent in db.scalars(select(PartnerApplication).where(PartnerApplication.card_id==row.id,PartnerApplication.status=='pending').with_for_update()):
        intent.status='cancelled';intent.active_key=None

def sync_recruitment(db,team,data,previous_need):
    if team.teammate_need=='none':
        close_recruitment(db,team);return
    linked=db.scalar(select(PartnerCard).where(PartnerCard.id==team.teammate_recruitment_id).with_for_update()) if team.teammate_recruitment_id else None
    if linked and linked.status=='hidden':fail('MODERATED','关联的队友招募已被隐藏，请先申请复核',409)
    changed=previous_need!=team.teammate_need
    if linked and changed:close_recruitment(db,team);linked=None
    if not linked:
        db.execute(select(User.id).where(User.id==team.owner_id).with_for_update())
        count=db.scalar(select(func.count(PartnerCard.id)).where(PartnerCard.owner_id==team.owner_id,PartnerCard.status=='active',PartnerCard.expires_at>now()))
        if count>=5:fail('LIMIT_REACHED','找队友卡片已达 5 张，请先结束一张，或选择无需招募',409)
        linked=PartnerCard(owner_id=team.owner_id,kind='recruit',role='fighter',target_role='priest' if team.teammate_need=='priest' else 'fighter',
            target_job='龙骑士' if team.teammate_need=='dragon_knight' else '',flower='any',level_min=1,level_max=300,expires_at=team.expires_at)
        db.add(linked)
    else:linked.version+=1
    if data.teammate_level_min is not None:linked.level_min=data.teammate_level_min
    if data.teammate_level_max is not None:linked.level_max=data.teammate_level_max
    if linked.level_min>linked.level_max:fail('INVALID_LEVEL_RANGE','队友最低等级不能大于最高等级',422)
    for key in ('game_id','level','map_name','start_time','end_time','notes'):setattr(linked,key,getattr(team,key))
    character=db.scalar(select(Character).where(Character.user_id==team.owner_id,Character.name==team.game_id))
    linked.job=character.job if character else ''
    linked.role='priest' if linked.job in ('牧师','祭司','主教') else 'fighter'
    linked.expires_at=team.expires_at
    db.flush();team.teammate_recruitment_id=linked.id
    save_contact(db,'partner',linked.id,data.contact.model_dump(),data.public_contact,team.expires_at+timedelta(days=7))

def delete_recruitment_contact(db,team):
    if not team.teammate_recruitment_id:return
    contact=db.scalar(select(Contact).where(Contact.resource=='partner',Contact.resource_id==team.teammate_recruitment_id).with_for_update())
    if contact:contact.encrypted='';contact.deleted_at=now()
