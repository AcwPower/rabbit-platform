"""Boss-count form and optional linked teammate recruitment."""
from alembic import op
import sqlalchemy as sa
revision='e64d713ca902'
down_revision='d78a42b61e09'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('partner_cards',sa.Column('target_job',sa.String(30),nullable=False,server_default=''))
    op.add_column('team_cards',sa.Column('teammate_need',sa.String(20),nullable=False,server_default='none'))
    op.add_column('team_cards',sa.Column('teammate_recruitment_id',sa.Integer(),nullable=True))
    op.create_foreign_key('fk_team_teammate_recruitment','team_cards','partner_cards',['teammate_recruitment_id'],['id'])
    op.create_unique_constraint('uq_team_teammate_recruitment','team_cards',['teammate_recruitment_id'])
    op.create_check_constraint('ck_team_teammate_need','team_cards',"teammate_need IN ('none','dragon_knight','priest')")
    op.create_check_constraint('ck_team_reserved_capacity','team_cards',"fighter_count + priest_count + confirmed_boss_count + (CASE WHEN teammate_need='none' THEN 0 ELSE 1 END) <= capacity")

def downgrade():
    op.drop_constraint('ck_team_reserved_capacity','team_cards',type_='check')
    op.drop_constraint('ck_team_teammate_need','team_cards',type_='check')
    op.drop_constraint('fk_team_teammate_recruitment','team_cards',type_='foreignkey')
    op.drop_constraint('uq_team_teammate_recruitment','team_cards',type_='unique')
    op.drop_column('team_cards','teammate_recruitment_id')
    op.drop_column('team_cards','teammate_need')
    op.drop_column('partner_cards','target_job')
