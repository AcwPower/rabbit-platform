"""Persist applicant and boss progress notifications, including guest owners."""
from alembic import op
import sqlalchemy as sa

revision = 'b903ed721a46'
down_revision = 'a782cd910f35'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('application_notifications',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('application_id',sa.Integer(),sa.ForeignKey('applications.id'),nullable=False),
        sa.Column('recipient_side',sa.String(12),nullable=False),
        sa.Column('event',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('read_at',sa.DateTime(),nullable=True),
        sa.UniqueConstraint('application_id','recipient_side','event',name='uq_application_notification'),
        sa.CheckConstraint("recipient_side IN ('owner','applicant')",name='ck_notification_side'))
    op.create_index('ix_application_notifications_application_id','application_notifications',['application_id'])
    op.create_index('ix_application_notifications_created_at','application_notifications',['created_at'])
    op.execute(sa.text("INSERT INTO application_notifications (application_id,recipient_side,event,created_at) "
        "SELECT a.id,'applicant','accepted',m.created_at FROM applications a JOIN matches m ON m.application_id=a.id "
        "WHERE a.status='accepted' AND m.status IN ('contacted','boarded') AND m.created_at>=UTC_TIMESTAMP()-INTERVAL 30 DAY"))
    op.execute(sa.text("INSERT INTO application_notifications (application_id,recipient_side,event,created_at) "
        "SELECT a.id,CASE WHEN a.card_type='team' THEN 'applicant' ELSE 'owner' END,'boarded',COALESCE(m.boarded_at,m.created_at) "
        "FROM applications a JOIN matches m ON m.application_id=a.id "
        "WHERE a.status='accepted' AND m.status='boarded' AND m.created_at>=UTC_TIMESTAMP()-INTERVAL 30 DAY"))

def downgrade():
    op.drop_table('application_notifications')
