"""add oidc_subject to users, drop password_hash

Revision ID: e15b4aad7f27
Revises: dd4af7b08b9d
Create Date: 2026-09-18 08:17:38.283065

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e15b4aad7f27'
down_revision = 'dd4af7b08b9d'
branch_labels = None
depends_on = None


def upgrade():
    # Hand-fixed: autogenerate left the unique constraint unnamed
    # (create_unique_constraint(None, ...)), which alembic itself warns
    # will fail to reverse cleanly -- named explicitly so downgrade() can
    # target it.
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('oidc_subject', sa.String(length=255), nullable=True))
        batch_op.create_unique_constraint('uq_users_oidc_subject', ['oidc_subject'])
        batch_op.drop_column('password_hash')


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('password_hash', sa.VARCHAR(length=255), autoincrement=False, nullable=True))
        batch_op.drop_constraint('uq_users_oidc_subject', type_='unique')
        batch_op.drop_column('oidc_subject')
