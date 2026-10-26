"""Support hourly game-coin prices; all existing prices remain RMB."""
from alembic import op
import sqlalchemy as sa

revision = 'a782cd910f35'
down_revision = 'f39a2e708b16'
branch_labels = None
depends_on = None

def upgrade():
    for table in ('team_cards','boss_cards'):
        op.add_column(table,sa.Column('price_currency',sa.String(8),nullable=False,server_default='rmb'))
        for column in ('price','night_price'):
            op.alter_column(table,column,existing_type=sa.Numeric(10,2),type_=sa.Numeric(16,2),existing_nullable=True)

def downgrade():
    # Currency removal would reinterpret game-coin amounts as RMB. Never silently
    # relabel financial terms or truncate prices during rollback.
    db=op.get_bind()
    for table in ('team_cards','boss_cards'):
        if db.scalar(sa.text(f"SELECT COUNT(*) FROM {table} WHERE price_currency!='rmb' OR price>99999999.99 OR night_price>99999999.99")):
            raise RuntimeError('Cannot downgrade while game-coin or oversized prices exist')
    for table in ('team_cards','boss_cards'):
        for column in ('price','night_price'):
            op.alter_column(table,column,existing_type=sa.Numeric(16,2),type_=sa.Numeric(10,2),existing_nullable=True)
        op.drop_column(table,'price_currency')
