"""add_menu_item_cost_price

Revision ID: cf71773784de
Revises: d2c8f1e4b7a9
Create Date: 2026-07-04 00:00:00.000000

Adds:
- menu_items.cost_price — estimated cost to produce one unit of the dish.
  Lets revenue/profit reporting compute COGS as
  SUM(order.quantity * menu_item.cost_price) without needing a full
  ingredient-level recipe/BOM (tracked separately as a future feature).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = 'cf71773784de'
down_revision: Union[str, Sequence[str], None] = 'd2c8f1e4b7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'menu_items',
        sa.Column('cost_price', sa.Float(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('menu_items', 'cost_price')
