"""add planning runs

Revision ID: 7c7e6c2f3a10
Revises: 019965ce4ab8
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "7c7e6c2f3a10"
down_revision: Union[str, Sequence[str], None] = "019965ce4ab8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "planning_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scenario", sa.String(length=80), nullable=False),
        sa.Column("target_date", sa.String(length=20), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("critic_verdict", sa.String(length=40), nullable=True),
        sa.Column("critic_score", sa.Float(), nullable=True),
        sa.Column("decision_log_id", sa.Integer(), nullable=True),
        sa.Column("final_response", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("recommendations", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("rag_context", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("critic", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("generated_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_planning_runs_created_at", "planning_runs", ["created_at"])
    op.create_index("ix_planning_runs_target_date", "planning_runs", ["target_date"])
    op.create_index("ix_planning_runs_status", "planning_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_planning_runs_status", table_name="planning_runs")
    op.drop_index("ix_planning_runs_target_date", table_name="planning_runs")
    op.drop_index("ix_planning_runs_created_at", table_name="planning_runs")
    op.drop_table("planning_runs")
