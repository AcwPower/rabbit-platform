"""Captain may silence reminders for a schedule without ending the booking."""
from alembic import op
import sqlalchemy as sa
revision='d125b0943c68'
down_revision='c014af832b57'
branch_labels=None
depends_on=None

def upgrade():
    op.add_column('matches',sa.Column('reminder_ignored_version',sa.Integer(),nullable=True))

def downgrade():
    op.drop_column('matches','reminder_ignored_version')
