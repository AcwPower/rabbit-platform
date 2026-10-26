"""Private character screenshots linked atomically to new accounts."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = 'c29b81e3a640'
down_revision = 'f0a63f1be60f'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('registration_proofs',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('encrypted_image', sa.Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False),
        sa.Column('game_id', sa.String(40), nullable=False),
        sa.Column('level', sa.Integer(), nullable=False),
        sa.Column('job', sa.String(30), nullable=False),
        sa.Column('confidence', sa.Text(), nullable=False),
        sa.Column('image_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.CheckConstraint('level BETWEEN 1 AND 300'))

def downgrade():
    op.drop_table('registration_proofs')
