import base64, hashlib, hmac, json, secrets
from datetime import timedelta
from fastapi import HTTPException, Request
from cryptography.fernet import Fernet
from sqlalchemy import select
from .config import settings
from .db import now
from .models import User, LoginSession, Challenge, Audit, Contact

cipher = Fernet(settings.contact_key.encode())

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def fail(code, message, status=400):
    raise HTTPException(status, {'code': code, 'message': message})

def hash_password(password):
    salt = secrets.token_bytes(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 600000)
    return 'pbkdf2$600000$' + base64.b64encode(salt).decode() + '$' + base64.b64encode(key).decode()

def check_password(password, stored):
    try:
        _, rounds, salt, expected = stored.split('$')
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), base64.b64decode(salt), int(rounds))
        return hmac.compare_digest(actual, base64.b64decode(expected))
    except (ValueError, TypeError):
        return False

def current_user(request, db, required=False):
    session = db.get(LoginSession, digest(request.cookies.get('rabbit_session', '')))
    user = db.get(User, session.user_id) if session and session.expires_at > now() else None
    if user and user.status != 'active':
        user = None
    if required and not user:
        fail('LOGIN_REQUIRED', '请先登录', 401)
    return user

def admin(request, db):
    user = current_user(request, db, True)
    if not user.is_admin:
        fail('FORBIDDEN', '需要管理员权限', 403)
    return user

def manager_token(request, required=False):
    token = request.headers.get('X-Manage-Token', '')
    if token and (len(token) < 40 or len(token) > 128 or not all(c.isalnum() or c in '-_' for c in token)):
        fail('INVALID_CREDENTIAL', '管理凭证无效', 403)
    if required and not token:
        fail('CREDENTIAL_REQUIRED', '缺少管理凭证', 403)
    return token

def owns(request, db, obj, attr='owner_id'):
    user = current_user(request, db)
    owner_id = getattr(obj, attr)
    if owner_id:
        return bool(user and user.id == owner_id)
    token = manager_token(request)
    return bool(token and obj.manage_hash and hmac.compare_digest(digest(token), obj.manage_hash))

def require_owner(request, db, obj, attr='owner_id'):
    if not owns(request, db, obj, attr):
        fail('FORBIDDEN', '没有此记录的管理权限', 403)

def actor(request, db):
    user = current_user(request, db)
    return f'user:{user.id}' if user else 'guest:' + digest(manager_token(request) or request.client.host)[:16]

def audit(db, request, action, resource, detail=''):
    db.add(Audit(actor=actor(request, db), action=action, resource=resource, detail=detail))

def verify_challenge(db, challenge_id, answer):
    challenge = db.scalar(select(Challenge).where(Challenge.id == challenge_id).with_for_update())
    if not challenge or challenge.used or challenge.expires_at <= now() or challenge.attempts >= 5:
        fail('CHALLENGE_EXPIRED', '验证已过期，请刷新验证题')
    challenge.attempts += 1
    if not hmac.compare_digest(challenge.answer_hash, digest(challenge.id + ':' + str(answer).strip())):
        db.commit()
        fail('CHALLENGE_WRONG', '验证答案不正确')
    challenge.used = True

def save_contact(db, resource, resource_id, value, public=False, expires=None):
    row = db.scalar(select(Contact).where(Contact.resource == resource, Contact.resource_id == resource_id).with_for_update())
    if not row:
        row = Contact(resource=resource, resource_id=resource_id)
        db.add(row)
    row.encrypted = cipher.encrypt(json.dumps(value, ensure_ascii=False).encode()).decode()
    row.public = public
    row.deleted_at = None
    row.expires_at = expires or now() + timedelta(days=7)

def read_contact(db, resource, resource_id, public_only=False):
    row = db.scalar(select(Contact).where(Contact.resource == resource, Contact.resource_id == resource_id))
    if not row or row.deleted_at or row.expires_at <= now() or (public_only and not row.public):
        return None
    return json.loads(cipher.decrypt(row.encrypted.encode()))
