"""Fighter/priest teammate recruitment and private contact requests."""
from alembic import op
import sqlalchemy as sa
revision='d78a42b61e09'
down_revision='c29b81e3a640'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('partner_cards',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('owner_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('kind',sa.String(12),nullable=False),sa.Column('role',sa.String(12),nullable=False),
        sa.Column('target_role',sa.String(12),nullable=False),sa.Column('game_id',sa.String(40),nullable=False),
        sa.Column('level',sa.Integer(),nullable=False),sa.Column('job',sa.String(30),nullable=False),
        sa.Column('map_name',sa.String(60),nullable=False),sa.Column('flower',sa.String(16),nullable=False),
        sa.Column('hourly_rate',sa.Numeric(16,2),nullable=True),sa.Column('price_currency',sa.String(8),nullable=True),
        sa.Column('level_min',sa.Integer(),nullable=False),sa.Column('level_max',sa.Integer(),nullable=False),
        sa.Column('start_time',sa.String(5),nullable=False),sa.Column('end_time',sa.String(5),nullable=False),
        sa.Column('notes',sa.String(600),nullable=False),sa.Column('status',sa.String(16),nullable=False),
        sa.Column('created_at',sa.DateTime(),nullable=False),sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.Column('version',sa.Integer(),nullable=False),
        sa.CheckConstraint("role IN ('fighter','priest')"),
        sa.CheckConstraint("(kind='recruit' AND target_role IN ('fighter','priest')) OR (kind='job' AND role='priest' AND target_role='any')"),
        sa.CheckConstraint("flower IN ('active','afk','any') AND (kind='recruit' OR flower!='any')"),
        sa.CheckConstraint("(kind='job' AND hourly_rate IS NOT NULL AND price_currency IS NOT NULL AND hourly_rate>0 AND price_currency IN ('rmb','meso')) OR (kind='recruit' AND hourly_rate IS NULL AND price_currency IS NULL)"),
        sa.CheckConstraint('level BETWEEN 1 AND 300 AND level_min BETWEEN 1 AND 300 AND level_max BETWEEN level_min AND 300'))
    for col in ('owner_id','status','created_at','expires_at'):op.create_index('ix_partner_cards_'+col,'partner_cards',[col])
    op.create_table('partner_applications',
        sa.Column('id',sa.Integer(),primary_key=True),
        sa.Column('card_id',sa.Integer(),sa.ForeignKey('partner_cards.id'),nullable=False),
        sa.Column('applicant_id',sa.Integer(),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('active_key',sa.String(64),unique=True),
        sa.Column('role',sa.String(12),nullable=False),sa.Column('game_id',sa.String(40),nullable=False),
        sa.Column('level',sa.Integer(),nullable=False),sa.Column('job',sa.String(30),nullable=False),
        sa.Column('flower',sa.String(16),nullable=False),sa.Column('notes',sa.String(400),nullable=False),
        sa.Column('status',sa.String(16),nullable=False),sa.Column('created_at',sa.DateTime(),nullable=False),
        sa.Column('expires_at',sa.DateTime(),nullable=False),
        sa.Column('joined_at',sa.DateTime(),nullable=True),
        sa.CheckConstraint("role IN ('fighter','priest')"),sa.CheckConstraint('level BETWEEN 1 AND 300'),
        sa.CheckConstraint("(role='fighter' AND flower='none') OR (role='priest' AND flower IN ('active','afk'))"))
    for col in ('card_id','applicant_id','status','expires_at'):op.create_index('ix_partner_applications_'+col,'partner_applications',[col])

def downgrade():
    op.drop_table('partner_applications')
    op.drop_table('partner_cards')
