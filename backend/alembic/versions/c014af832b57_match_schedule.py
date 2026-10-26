"""Boss booking schedules, preserving actual boarding timestamps."""
from alembic import op
import sqlalchemy as sa

revision = 'c014af832b57'
down_revision = 'b903ed721a46'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('applications',sa.Column('requested_start_at',sa.DateTime(),nullable=True))
    op.add_column('applications',sa.Column('duration_hours',sa.Integer(),nullable=True))
    op.add_column('matches',sa.Column('planned_start_at',sa.DateTime(),nullable=True))
    op.add_column('matches',sa.Column('expected_end_at',sa.DateTime(),nullable=True))
    op.add_column('matches',sa.Column('schedule_version',sa.Integer(),nullable=False,server_default='1'))
    from app.schedule import default_end_at
    db=op.get_bind()
    for row in db.execute(sa.text("SELECT m.id,m.boarded_at,t.end_time FROM matches m JOIN team_cards t ON t.id=m.team_id WHERE m.boarded_at IS NOT NULL")).mappings().all():
        db.execute(sa.text('UPDATE matches SET planned_start_at=:start,expected_end_at=:end WHERE id=:id'),{'id':row['id'],'start':row['boarded_at'],'end':default_end_at(row['boarded_at'],row['end_time'])})

def downgrade():
    op.drop_column('applications','duration_hours')
    op.drop_column('applications','requested_start_at')
    op.drop_column('matches','planned_start_at')
    op.drop_column('matches','schedule_version')
    op.drop_column('matches','expected_end_at')
