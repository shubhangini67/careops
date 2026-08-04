"""add_feedback_external_order_id_and_connector_metadata

Revision ID: d2c8f1e4b7a9
Revises: b3e1f2a9c5d7
Create Date: 2026-06-29 00:00:00.000000

Adds:
- feedback.external_order_id  — dedup key for Swiggy delivery feedback sync
- connectors.connector_metadata JSONB — stores per-connector metadata (e.g. Dineout booking IDs)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = 'd2c8f1e4b7a9'
down_revision: Union[str, Sequence[str], None] = 'b3e1f2a9c5d7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'feedback',
        sa.Column('external_order_id', sa.String(length=200), nullable=True),
    )
    op.add_column(
        'connectors',
        sa.Column('connector_metadata', JSONB(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('connectors', 'connector_metadata')
    op.drop_column('feedback', 'external_order_id')
