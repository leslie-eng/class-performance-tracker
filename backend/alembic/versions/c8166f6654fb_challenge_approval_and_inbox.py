"""challenge approval and inbox

Revision ID: c8166f6654fb
Revises: f233d4c326a4
Create Date: 2026-10-12 19:27:47.722280

Existing challenges become `approved` (through the column default), so nothing that's
live today disappears. The default stays: code from before this release, still serving
during a deploy, creates challenges without a status, and only admins could do that.
New code always sets the status itself.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c8166f6654fb'
down_revision: Union[str, Sequence[str], None] = 'f233d4c326a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

STATUS = sa.Enum('pending', 'approved', 'rejected', 'cancelled', name='challengestatus', native_enum=False, length=32)


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('inbox_messages',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('event', sa.String(length=40), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('body', sa.Text(), nullable=False),
    sa.Column('link', sa.String(length=300), nullable=True),
    sa.Column('challenge_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['challenge_id'], ['challenges.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inbox_messages_user_read', 'inbox_messages', ['user_id', 'read_at'], unique=False)

    # Batch mode: plain ALTERs on Postgres, a table copy on SQLite (which can't add foreign keys).
    with op.batch_alter_table('challenges') as batch:
        batch.add_column(sa.Column('status', STATUS, nullable=False, server_default='approved'))
        batch.add_column(sa.Column('created_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('reviewed_by', sa.Integer(), nullable=True))
        batch.add_column(sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column('review_note', sa.Text(), nullable=True))
        batch.create_foreign_key('fk_challenges_created_by_users', 'users', ['created_by'], ['id'], ondelete='SET NULL')
        batch.create_foreign_key('fk_challenges_reviewed_by_users', 'users', ['reviewed_by'], ['id'], ondelete='SET NULL')
        batch.create_index('ix_challenges_status', ['status'], unique=False)

    # Backfill: existing challenges were all created by admins and were live, so they count as approved
    # (done by the default above). Who created or reviewed them wasn't recorded, so those stay empty.
    op.execute("UPDATE challenges SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table('challenges') as batch:
        batch.alter_column('updated_at', existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    """Downgrade schema. Pending, rejected and cancelled proposals would become live challenges,
    so they're deleted first."""
    op.execute("DELETE FROM challenges WHERE status <> 'approved'")
    with op.batch_alter_table('challenges') as batch:
        batch.drop_index('ix_challenges_status')
        batch.drop_constraint('fk_challenges_reviewed_by_users', type_='foreignkey')
        batch.drop_constraint('fk_challenges_created_by_users', type_='foreignkey')
        batch.drop_column('review_note')
        batch.drop_column('reviewed_at')
        batch.drop_column('reviewed_by')
        batch.drop_column('updated_at')
        batch.drop_column('created_by')
        batch.drop_column('status')
    op.drop_index('ix_inbox_messages_user_read', table_name='inbox_messages')
    op.drop_table('inbox_messages')
