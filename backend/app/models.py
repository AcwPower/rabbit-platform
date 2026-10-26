from sqlalchemy import (Column, Integer, String, Text, DateTime, Boolean, Numeric, ForeignKey,
                        UniqueConstraint, CheckConstraint, Index)
from .db import Base, now
from sqlalchemy.dialects.mysql import MEDIUMTEXT

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(40), unique=True, nullable=False)
    password_hash = Column(String(256), nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    status = Column(String(16), nullable=False, default='active')
    created_at = Column(DateTime, nullable=False, default=now)

class LoginSession(Base):
    __tablename__ = 'sessions'
    token_hash = Column(String(64), primary_key=True)
    user_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    csrf = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)

class AccountContact(Base):
    __tablename__ = 'account_contacts'
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    encrypted = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False)
    changed_at = Column(DateTime, nullable=True)

class RegistrationProof(Base):
    __tablename__ = 'registration_proofs'
    user_id = Column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    encrypted_image = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False)
    game_id = Column(String(40), nullable=False)
    level = Column(Integer, nullable=False)
    job = Column(String(30), nullable=False)
    confidence = Column(Text, nullable=False)
    image_hash = Column(String(64), nullable=False)
    created_at = Column(DateTime, nullable=False, default=now)
    __table_args__ = (CheckConstraint('level BETWEEN 1 AND 300'),)

class Character(Base):
    __tablename__ = 'game_characters'
    id = Column(Integer, primary_key=True)
    user_id = Column(ForeignKey('users.id'), nullable=False)
    name = Column(String(40), nullable=False)
    level = Column(Integer, nullable=False)
    job = Column(String(30), nullable=False, default='')
    __table_args__ = (UniqueConstraint('user_id', 'name'), CheckConstraint('level BETWEEN 1 AND 300'))

class PartnerCard(Base):
    __tablename__ = 'partner_cards'
    id = Column(Integer, primary_key=True)
    owner_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    kind = Column(String(12), nullable=False, default='recruit')
    role = Column(String(12), nullable=False)
    target_role = Column(String(12), nullable=False, default='fighter')
    target_job = Column(String(30), nullable=False, default='', server_default='')
    game_id = Column(String(40), nullable=False)
    level = Column(Integer, nullable=False)
    job = Column(String(30), nullable=False, default='')
    map_name = Column(String(60), nullable=False, default='')
    flower = Column(String(16), nullable=False, default='any')
    hourly_rate = Column(Numeric(16,2), nullable=True)
    price_currency = Column(String(8), nullable=True)
    level_min = Column(Integer, nullable=False, default=1)
    level_max = Column(Integer, nullable=False, default=300)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)
    notes = Column(String(600), nullable=False, default='')
    status = Column(String(16), nullable=False, default='active', index=True)
    created_at = Column(DateTime, nullable=False, default=now, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)
    __table_args__ = (CheckConstraint("role IN ('fighter','priest')"),
        CheckConstraint("(kind='recruit' AND target_role IN ('fighter','priest')) OR (kind='job' AND role='priest' AND target_role='any')"),
        CheckConstraint("flower IN ('active','afk','any') AND (kind='recruit' OR flower!='any')"),
        CheckConstraint("(kind='job' AND hourly_rate IS NOT NULL AND price_currency IS NOT NULL AND hourly_rate>0 AND price_currency IN ('rmb','meso')) OR (kind='recruit' AND hourly_rate IS NULL AND price_currency IS NULL)"),
        CheckConstraint('level BETWEEN 1 AND 300 AND level_min BETWEEN 1 AND 300 AND level_max BETWEEN level_min AND 300'))

class PartnerApplication(Base):
    __tablename__ = 'partner_applications'
    id = Column(Integer, primary_key=True)
    card_id = Column(ForeignKey('partner_cards.id'), nullable=False, index=True)
    applicant_id = Column(ForeignKey('users.id'), nullable=False, index=True)
    active_key = Column(String(64), nullable=True, unique=True)
    role = Column(String(12), nullable=False)
    game_id = Column(String(40), nullable=False)
    level = Column(Integer, nullable=False)
    job = Column(String(30), nullable=False, default='')
    flower = Column(String(16), nullable=False, default='none')
    notes = Column(String(400), nullable=False, default='')
    status = Column(String(16), nullable=False, default='pending', index=True)
    created_at = Column(DateTime, nullable=False, default=now)
    expires_at = Column(DateTime, nullable=False, index=True)
    joined_at = Column(DateTime, nullable=True)
    __table_args__ = (CheckConstraint("role IN ('fighter','priest')"),CheckConstraint('level BETWEEN 1 AND 300'),
        CheckConstraint("(role='fighter' AND flower='none') OR (role='priest' AND flower IN ('active','afk'))"))

class CardFields:
    id = Column(Integer, primary_key=True)
    owner_id = Column(ForeignKey('users.id'), nullable=True, index=True)
    manage_hash = Column(String(64), nullable=True)
    game_id = Column(String(40), nullable=False)
    level = Column(Integer, nullable=False)
    map_name = Column(String(60), nullable=False)
    capacity = Column(Integer, nullable=False)
    flower = Column(String(16), nullable=False)
    price_mode = Column(String(16), nullable=False)
    price_currency = Column(String(8), nullable=False, default='rmb', server_default='rmb')
    price = Column(Numeric(16,2), nullable=True)
    night_price = Column(Numeric(16,2), nullable=True)
    exp_min = Column(Integer, nullable=False)
    exp_max = Column(Integer, nullable=False)
    start_time = Column(String(5), nullable=False)
    end_time = Column(String(5), nullable=False)
    notes = Column(String(600), nullable=False, default='')
    status = Column(String(16), nullable=False, default='active', index=True)
    created_at = Column(DateTime, nullable=False, default=now, index=True)
    expires_at = Column(DateTime, nullable=False, index=True)
    version = Column(Integer, nullable=False, default=1)

class TeamCard(CardFields, Base):
    __tablename__ = 'team_cards'
    fighter_count = Column(Integer, nullable=False, default=1)
    priest_count = Column(Integer, nullable=False, default=0)
    confirmed_boss_count = Column(Integer, nullable=False, default=0)
    level_min = Column(Integer, nullable=False)
    level_max = Column(Integer, nullable=False)
    teammate_need = Column(String(20), nullable=False, default='none', server_default='none')
    teammate_recruitment_id = Column(ForeignKey('partner_cards.id',name='fk_team_teammate_recruitment'), nullable=True)
    __table_args__ = (CheckConstraint('capacity BETWEEN 2 AND 6'),
        CheckConstraint('fighter_count >= 1 AND priest_count >= 0 AND confirmed_boss_count >= 0'),
        CheckConstraint('fighter_count + priest_count + confirmed_boss_count <= capacity'),
        CheckConstraint('exp_min <= exp_max AND level_min <= level_max'),
        CheckConstraint("teammate_need IN ('none','dragon_knight','priest')",name='ck_team_teammate_need'),
        UniqueConstraint('teammate_recruitment_id',name='uq_team_teammate_recruitment'),
        CheckConstraint("fighter_count + priest_count + confirmed_boss_count + (CASE WHEN teammate_need='none' THEN 0 ELSE 1 END) <= capacity",name='ck_team_reserved_capacity'))

class BossCard(CardFields, Base):
    __tablename__ = 'boss_cards'
    __table_args__ = (CheckConstraint('capacity BETWEEN 2 AND 6'), CheckConstraint('exp_min <= exp_max'))

class Application(Base):
    __tablename__ = 'applications'
    id = Column(Integer, primary_key=True)
    card_type = Column(String(8), nullable=False)
    team_card_id = Column(ForeignKey('team_cards.id'), nullable=True, index=True)
    boss_card_id = Column(ForeignKey('boss_cards.id'), nullable=True, index=True)
    offered_team_id = Column(ForeignKey('team_cards.id'), nullable=True)
    applicant_id = Column(ForeignKey('users.id'), nullable=True, index=True)
    manage_hash = Column(String(64), nullable=True)
    active_key = Column(String(64), nullable=True, unique=True)
    game_id = Column(String(40), nullable=False)
    level = Column(Integer, nullable=True)
    source = Column(String(16), nullable=False, default='web', server_default='web')
    requested_start_at = Column(DateTime, nullable=True)
    duration_hours = Column(Integer, nullable=True)
    notes = Column(String(400), nullable=False, default='')
    status = Column(String(16), nullable=False, default='pending', index=True)
    created_at = Column(DateTime, nullable=False, default=now)
    expires_at = Column(DateTime, nullable=False, index=True)
    __table_args__ = (CheckConstraint('(team_card_id IS NOT NULL AND boss_card_id IS NULL) OR (team_card_id IS NULL AND boss_card_id IS NOT NULL)'),)

class Match(Base):
    __tablename__ = 'matches'
    id = Column(Integer, primary_key=True)
    application_id = Column(ForeignKey('applications.id'), unique=True, nullable=False)
    team_id = Column(ForeignKey('team_cards.id'), nullable=False)
    status = Column(String(16), nullable=False, default='contacted')
    owner_complete = Column(Boolean, nullable=False, default=False)
    applicant_complete = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, default=now)
    boarded_at = Column(DateTime, nullable=True)
    planned_start_at = Column(DateTime, nullable=True)
    expected_end_at = Column(DateTime, nullable=True)
    schedule_version = Column(Integer, nullable=False, default=1, server_default='1')
    finished_at = Column(DateTime, nullable=True)
    reminder_ignored_version = Column(Integer, nullable=True)

class ApplicationNotification(Base):
    __tablename__ = 'application_notifications'
    id = Column(Integer, primary_key=True)
    application_id = Column(ForeignKey('applications.id'), nullable=False, index=True)
    recipient_side = Column(String(12), nullable=False)
    event = Column(String(16), nullable=False)
    created_at = Column(DateTime, nullable=False, default=now, index=True)
    read_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('application_id','recipient_side','event',name='uq_application_notification'),
        CheckConstraint("recipient_side IN ('owner','applicant')",name='ck_notification_side'))

class Contact(Base):
    __tablename__ = 'contact_methods'
    id = Column(Integer, primary_key=True)
    resource = Column(String(12), nullable=False)
    resource_id = Column(Integer, nullable=False)
    encrypted = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False)
    public = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    __table_args__ = (UniqueConstraint('resource', 'resource_id'),)

class Review(Base):
    __tablename__ = 'reviews'
    id = Column(Integer, primary_key=True)
    match_id = Column(ForeignKey('matches.id'), nullable=False)
    author_side = Column(String(12), nullable=False)
    target_user_id = Column(ForeignKey('users.id'), nullable=True, index=True)
    tags = Column(String(200), nullable=False)
    body = Column(String(500), nullable=False, default='')
    status = Column(String(16), nullable=False, default='pending')
    created_at = Column(DateTime, nullable=False, default=now)
    __table_args__ = (UniqueConstraint('match_id', 'author_side'),)

class Report(Base):
    __tablename__ = 'reports'
    id = Column(Integer, primary_key=True)
    resource = Column(String(16), nullable=False)
    resource_id = Column(Integer, nullable=False)
    reason = Column(String(600), nullable=False)
    reporter_hash = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default='pending')
    decision = Column(String(500), nullable=False, default='')
    created_at = Column(DateTime, nullable=False, default=now)

class Audit(Base):
    __tablename__ = 'audit_logs'
    id = Column(Integer, primary_key=True)
    actor = Column(String(80), nullable=False)
    action = Column(String(80), nullable=False)
    resource = Column(String(80), nullable=False)
    detail = Column(String(500), nullable=False, default='')
    created_at = Column(DateTime, nullable=False, default=now)

class Challenge(Base):
    __tablename__ = 'challenges'
    id = Column(String(48), primary_key=True)
    answer_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False, index=True)
    attempts = Column(Integer, nullable=False, default=0)
    used = Column(Boolean, nullable=False, default=False)

class RequestKey(Base):
    __tablename__ = 'idempotency_keys'
    key_hash = Column(String(64), primary_key=True)
    request_hash = Column(String(64), nullable=False)
    status_code = Column(Integer, nullable=False, default=0)
    response = Column(Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=True)
    created_at = Column(DateTime, nullable=False, default=now, index=True)

class RateBucket(Base):
    __tablename__ = 'rate_buckets'
    id = Column(String(64), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    expires_at = Column(DateTime, nullable=False, index=True)

class Recovery(Base):
    __tablename__ = 'recovery_channels'
    id = Column(Integer, primary_key=True)
    resource = Column(String(12), nullable=False)
    resource_id = Column(Integer, nullable=False)
    email_encrypted = Column(Text, nullable=False)
    email_hash = Column(String(64), nullable=False, index=True)
    code_hash = Column(String(64), nullable=True)
    verified = Column(Boolean, nullable=False, default=False)
    expires_at = Column(DateTime, nullable=True)
    attempts = Column(Integer, nullable=False, default=0)
    __table_args__ = (UniqueConstraint('resource', 'resource_id'),)
