"""Allow captain-entered screenshot members without invented character levels."""
from alembic import op
import sqlalchemy as sa
revision='e236ca105d79'
down_revision='d125b0943c68'
branch_labels=None
depends_on=None
def upgrade():
    op.add_column('applications',sa.Column('source',sa.String(16),nullable=False,server_default='web'))
    op.alter_column('applications','level',existing_type=sa.Integer(),nullable=True)
def downgrade():
    # Unknown levels must be resolved before removing this feature's schema.
    connection=op.get_bind()
    if connection.execute(sa.text('SELECT COUNT(*) FROM applications WHERE level IS NULL')).scalar():
        raise RuntimeError('Resolve unknown screenshot member levels before downgrade')
    op.alter_column('applications','level',existing_type=sa.Integer(),nullable=False)
    op.drop_column('applications','source')
