"""add_connectors_table_and_order_source_channel

Revision ID: b3e1f2a9c5d7
Revises: f696f1eee5fc
Create Date: 2026-06-27 00:00:00.000000

Adds:
- connectors table (per-org external platform registry)
- orders.source, orders.channel, orders.external_order_id
- reservations.source, reservations.external_booking_id
- feedback.delivery_time_actual_mins, feedback.delivery_time_promised_mins, feedback.was_late
- swiggy_delivery to feedbacksource enum
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'b3e1f2a9c5d7'
down_revision: Union[str, Sequence[str], None] = 'f696f1eee5fc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── connectors table ──────────────────────────────────────────────────────
    op.create_table(
        'connectors',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('org_id', sa.Integer(), nullable=False),
        sa.Column('connector_type', sa.String(length=50), nullable=False),
        sa.Column('access_token_encrypted', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.DateTime(), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('sync_status', sa.String(length=20), nullable=False, server_default='never_synced'),
        sa.Column('error_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['org_id'], ['organizations.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('org_id', 'connector_type', name='uq_connector_org_type'),
    )

    # ── orders: source, channel, external_order_id ───────────────────────────
    op.add_column('orders', sa.Column('source', sa.String(length=50), nullable=False, server_default='internal'))
    op.add_column('orders', sa.Column('channel', sa.String(length=50), nullable=False, server_default='dine_in'))
    op.add_column('orders', sa.Column('external_order_id', sa.String(length=200), nullable=True))
    op.create_unique_constraint('uq_order_external_id', 'orders', ['external_order_id'])

    # ── reservations: source, external_booking_id ─────────────────────────────
    op.add_column('reservations', sa.Column('source', sa.String(length=50), nullable=False, server_default='internal'))
    op.add_column('reservations', sa.Column('external_booking_id', sa.String(length=200), nullable=True))

    # ── feedback: delivery timing columns ─────────────────────────────────────
    op.add_column('feedback', sa.Column('delivery_time_actual_mins', sa.Integer(), nullable=True))
    op.add_column('feedback', sa.Column('delivery_time_promised_mins', sa.Integer(), nullable=True))
    op.add_column('feedback', sa.Column('was_late', sa.Boolean(), nullable=True))

    # ── feedbacksource enum: add swiggy_delivery ──────────────────────────────
    # PostgreSQL requires ALTER TYPE to add enum values
    op.execute("ALTER TYPE feedbacksource ADD VALUE IF NOT EXISTS 'swiggy_delivery'")


def downgrade() -> None:
    op.drop_column('feedback', 'was_late')
    op.drop_column('feedback', 'delivery_time_promised_mins')
    op.drop_column('feedback', 'delivery_time_actual_mins')

    op.drop_column('reservations', 'external_booking_id')
    op.drop_column('reservations', 'source')

    op.drop_constraint('uq_order_external_id', 'orders', type_='unique')
    op.drop_column('orders', 'external_order_id')
    op.drop_column('orders', 'channel')
    op.drop_column('orders', 'source')

    op.drop_table('connectors')
    # Note: PostgreSQL does not support removing enum values — swiggy_delivery stays
