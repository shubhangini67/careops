"""Alembic migration: CareOps hospital operations tables."""

from alembic import op
import sqlalchemy as sa


revision = "c0a1e0ps0001"
down_revision = "a1e96ebcb740"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "departments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("bed_limit", sa.Integer(), nullable=False, server_default="20"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "bed_capacity",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("total_beds", sa.Integer(), nullable=False),
        sa.Column("occupied_beds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "staff_shifts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("role", sa.Enum("doctors", "nurses", "support", name="staffrole"), nullable=False),
        sa.Column("headcount", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("shift_start", sa.DateTime(), nullable=False),
        sa.Column("shift_end", sa.DateTime(), nullable=False),
    )
    op.create_table(
        "supply_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("unit", sa.String(20), nullable=False),
        sa.Column("quantity_on_hand", sa.Float(), nullable=False),
        sa.Column("reorder_threshold", sa.Float(), nullable=False),
        sa.Column("is_critical", sa.Boolean(), server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "appointments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("department_id", sa.Integer(), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="booked"),
        sa.Column("encounter_type", sa.String(30), nullable=False, server_default="outpatient"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )
    op.create_table(
        "safety_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("org_id", sa.Integer(), sa.ForeignKey("organizations.id"), nullable=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("severity", sa.String(20), nullable=False, server_default="low"),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("sentiment", sa.String(20), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("safety_incidents")
    op.drop_table("appointments")
    op.drop_table("supply_items")
    op.drop_table("staff_shifts")
    op.drop_table("bed_capacity")
    op.drop_table("departments")
    op.execute("DROP TYPE IF EXISTS staffrole")
