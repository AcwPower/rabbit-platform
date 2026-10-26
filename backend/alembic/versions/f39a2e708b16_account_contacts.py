"""Account WeChat profiles with a server-enforced seven-day edit interval."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.mysql import MEDIUMTEXT

revision = 'f39a2e708b16'
down_revision = 'e64d713ca902'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('account_contacts',
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
        sa.Column('encrypted', sa.Text().with_variant(MEDIUMTEXT(), 'mysql'), nullable=False),
        sa.Column('changed_at', sa.DateTime(), nullable=True))
    # Preserve the latest existing WeChat per account. NULL allows one immediate
    # correction after rollout; subsequent successful changes start the 7-day clock.
    links = []
    for resource, table, owner in [('team', 'team_cards', 'owner_id'), ('boss', 'boss_cards', 'owner_id'),
            ('application', 'applications', 'applicant_id'), ('partner', 'partner_cards', 'owner_id'),
            ('partner_app', 'partner_applications', 'applicant_id')]:
        links.append(f"SELECT r.{owner} AS user_id, c.id FROM contact_methods c JOIN {table} r ON r.id=c.resource_id "
                     f"WHERE c.resource='{resource}' AND r.{owner} IS NOT NULL AND c.deleted_at IS NULL AND c.expires_at>UTC_TIMESTAMP()")
    op.execute(sa.text('INSERT INTO account_contacts (user_id, encrypted, changed_at) '
        'SELECT latest.user_id, c.encrypted, NULL FROM (SELECT user_id, MAX(id) AS contact_id FROM ('
        + ' UNION ALL '.join(links) + ') links GROUP BY user_id) latest '
        'JOIN contact_methods c ON c.id=latest.contact_id'))

def downgrade():
    op.drop_table('account_contacts')
