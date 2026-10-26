import json
from datetime import timedelta
from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select, or_
from .db import get_db, now
from .models import User, AccountContact, Contact, Character, TeamCard, BossCard, Application, PartnerCard, PartnerApplication, Report
from .schemas import ContactInput, CharacterInput, Input
from .security import current_user, admin, cipher, fail, audit, digest
from .services import iso

router = APIRouter()

def owned_contacts(user_id):
    return or_(*[(Contact.resource == resource) & Contact.resource_id.in_(select(model.id).where(getattr(model, owner) == user_id))
                 for resource, model, owner in [('team', TeamCard, 'owner_id'), ('boss', BossCard, 'owner_id'),
                     ('application', Application, 'applicant_id'), ('partner', PartnerCard, 'owner_id'),
                     ('partner_app', PartnerApplication, 'applicant_id')]])

def decode_contact(row):
    return json.loads(cipher.decrypt(row.encrypted.encode())) if row else None

def lock_account(db, user_id):
    # Serialize first saves and edits, including accounts without a contact row yet.
    db.execute(select(User.id).where(User.id == user_id).with_for_update())
    return db.scalar(select(AccountContact).where(AccountContact.user_id == user_id).with_for_update().execution_options(populate_existing=True))

def account_contact(db, request, user, submitted):
    value = submitted.model_dump()
    if not user:
        return value
    row = lock_account(db, user.id)
    if row:
        current = decode_contact(row)
        if current != value:
            fail('CONTACT_PROFILE_REQUIRED', '请在「我的资料」修改微信资料，每 7 天最多修改一次；刷新表单可带入当前微信', 409)
        return current
    db.add(AccountContact(user_id=user.id, encrypted=cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode(), changed_at=now()))
    db.flush()
    audit(db, request, 'profile_contact_saved', f'user:{user.id}', '首次保存微信资料')
    return value

def profile_dict(db, user):
    row = db.get(AccountContact, user.id)
    next_change = row.changed_at + timedelta(days=7) if row and row.changed_at else None
    chars = db.scalars(select(Character).where(Character.user_id == user.id).order_by(Character.id)).all()
    requests = db.scalars(select(Report).where(Report.resource == 'appeal', Report.resource_id == user.id,
        Report.reporter_hash == digest(f'user:{user.id}'),
        Report.reason.startswith('角色资料修改申请：')).order_by(Report.id.desc()).limit(5)).all()
    return {'username': user.username, 'contact': decode_contact(row), 'contact_changed_at': iso(row.changed_at) if row else None,
            'contact_next_change_at': iso(next_change), 'can_edit_contact': not next_change or next_change <= now(),
            'characters': [{'id': c.id, 'name': c.name, 'level': c.level, 'job': c.job} for c in chars],
            'character_requests': [{'id': r.id, 'status': r.status, 'decision': r.decision, 'created_at': iso(r.created_at)} for r in requests]}

@router.get('/profile')
def get_profile(request: Request, db=Depends(get_db)):
    return profile_dict(db, current_user(request, db, True))

@router.put('/profile/contact')
def update_contact(data: ContactInput, request: Request, db=Depends(get_db)):
    user = current_user(request, db, True)
    row = lock_account(db, user.id)
    value = data.model_dump()
    if row and decode_contact(row) == value:
        return profile_dict(db, user)
    if row and row.changed_at and row.changed_at + timedelta(days=7) > now():
        fail('CONTACT_CHANGE_LIMIT', '微信资料每 7 天最多修改一次，请在下次可修改时间后再试', 429)
    encrypted = cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()
    if not row:
        row = AccountContact(user_id=user.id)
        db.add(row)
    row.encrypted = encrypted
    row.changed_at = now()
    # Keep existing, still-visible contact snapshots in sync without reviving deleted ones
    # or changing who is allowed to see them.
    for contact in db.scalars(select(Contact).where(owned_contacts(user.id), Contact.deleted_at.is_(None), Contact.expires_at > now()).with_for_update()):
        contact.encrypted = encrypted
    db.flush()
    audit(db, request, 'profile_contact_changed', f'user:{user.id}', '微信资料已更新（不记录联系方式内容）')
    return profile_dict(db, user)

class CharacterRequest(CharacterInput):
    reason: str = Field(min_length=3, max_length=350)

@router.post('/profile/character-request')
def request_character_change(data: CharacterRequest, request: Request, db=Depends(get_db)):
    user = current_user(request, db, True)
    lock_account(db, user.id)
    pending = db.scalar(select(Report.id).where(Report.resource == 'appeal', Report.resource_id == user.id,
        Report.reporter_hash == digest(f'user:{user.id}'),
        Report.status == 'pending', Report.reason.startswith('角色资料修改申请：')))
    if pending:
        fail('REQUEST_PENDING', '已有角色修改申请等待管理员处理，请勿重复提交', 409)
    row = Report(resource='appeal', resource_id=user.id, reporter_hash=digest(f'user:{user.id}'),
        reason=f'角色资料修改申请：游戏 ID {data.name}；等级 {data.level}；职业 {data.job or "未填写"}。原因：{data.reason}')
    db.add(row); db.flush()
    audit(db, request, 'character_change_requested', f'user:{user.id}')
    return {'id': row.id, 'status': 'pending'}

@router.get('/admin/users/{user_id}/characters')
def admin_characters(user_id: int, request: Request, db=Depends(get_db)):
    admin(request, db)
    return [{'id': c.id, 'name': c.name, 'level': c.level, 'job': c.job} for c in
            db.scalars(select(Character).where(Character.user_id == user_id).order_by(Character.id))]

@router.put('/admin/users/{user_id}/characters/{character_id}')
def admin_change_character(user_id: int, character_id: int, data: CharacterRequest, request: Request, db=Depends(get_db)):
    admin(request, db)
    row = db.scalar(select(Character).where(Character.id == character_id, Character.user_id == user_id).with_for_update())
    if not row:
        fail('NOT_FOUND', '角色资料不存在', 404)
    old = f'{row.name} / Lv.{row.level} / {row.job}'
    for field in ('name', 'level', 'job'):
        setattr(row, field, getattr(data, field))
    audit(db, request, 'admin_character_changed', f'user:{user_id}',
          f'{old} → {row.name} / Lv.{row.level} / {row.job}；依据：{data.reason}'[:500])
    return {'ok': True}
