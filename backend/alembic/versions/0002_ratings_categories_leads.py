"""custom rating parameters, call categories, leads

Revision ID: 0002_ratings_categories_leads
Revises: 0001_initial_schema
Create Date: 2026-09-16 22:53:02.503386
"""
from __future__ import annotations

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime

import sqlalchemy as sa

from alembic import op

revision: str = "0002_ratings_categories_leads"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Seeded for every existing org (and read by scripts/seed.py for new ones) so
# the feature has sensible content on day one instead of an empty settings
# screen. "Other" is the fallback the pipeline resolves to when the model's
# category doesn't match anything configured — see app/services/pipeline.py.
DEFAULT_CATEGORIES = [
    ("Sales Enquiry", "A prospective customer asking about pricing, plans or a purchase.", False),
    ("Vendor Call", "A supplier, vendor or partner call, not a customer.", False),
    ("Transactional", "Billing, invoices, order status, renewals — routine account business.",
     False),
    ("Support Request", "An existing customer needs help with a problem.", False),
    ("Complaint", "A customer registering dissatisfaction or escalating an issue.", False),
    ("Other", "Doesn't fit any other category — wrong numbers, spam, internal calls.", True),
]
DEFAULT_RATING_PARAMETERS = [
    ("Politeness", "Courtesy and tone shown to the customer throughout the call.", 1, 5),
    ("Resolution Effectiveness", "How directly the call addressed what the customer needed.",
     1, 5),
    ("Product Knowledge", "Accuracy and confidence of the agent's answers.", 1, 5),
    ("Professionalism", "Overall conduct — pacing, clarity, and handling of the conversation.",
     1, 5),
]


def upgrade() -> None:
    # ### schema ###
    op.create_table(
        "call_categories",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_call_categories_org_name"),
    )
    with op.batch_alter_table("call_categories", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_call_categories_created_by_user_id"),
            ["created_by_user_id"], unique=False,
        )
        batch_op.create_index(
            "ix_call_categories_org_active", ["org_id", "is_active"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_call_categories_org_id"), ["org_id"], unique=False)

    op.create_table(
        "rating_parameters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scale_min", sa.Integer(), nullable=False),
        sa.Column("scale_max", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_rating_parameters_org_name"),
    )
    with op.batch_alter_table("rating_parameters", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_rating_parameters_created_by_user_id"),
            ["created_by_user_id"], unique=False,
        )
        batch_op.create_index(
            "ix_rating_parameters_org_active", ["org_id", "is_active"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_rating_parameters_org_id"), ["org_id"], unique=False)

    op.create_table(
        "leads",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("call_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("customer_number", sa.String(length=20), nullable=False),
        sa.Column("customer_name", sa.String(length=160), nullable=True),
        sa.Column("lead_name", sa.String(length=160), nullable=True),
        sa.Column("lead_email", sa.String(length=254), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.Column("intent", sa.Text(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("source_quote", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("call_id", name="uq_leads_call"),
    )
    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_leads_agent_id"), ["agent_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_leads_call_id"), ["call_id"], unique=False)
        batch_op.create_index(
            "ix_leads_org_category_created", ["org_id", "category", "created_at"], unique=False
        )
        batch_op.create_index(batch_op.f("ix_leads_org_id"), ["org_id"], unique=False)

    with op.batch_alter_table("analyses", schema=None) as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.String(length=36), nullable=True))
        batch_op.add_column(sa.Column("category_name", sa.String(length=120), nullable=True))
        batch_op.add_column(sa.Column("category_confidence", sa.Float(), nullable=True))
        # server_default backfills existing analysis rows with an empty list;
        # the ORM's Python-side `default=list` only applies to new inserts.
        batch_op.add_column(
            sa.Column("custom_ratings", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.create_index(batch_op.f("ix_analyses_category_id"), ["category_id"], unique=False)
        batch_op.create_foreign_key(
            "fk_analyses_category_id", "call_categories", ["category_id"], ["id"],
            ondelete="SET NULL",
        )

    # ### seed defaults for every existing org ###
    call_categories = sa.table(
        "call_categories",
        sa.column("id", sa.String),
        sa.column("org_id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("is_active", sa.Boolean),
        sa.column("is_default", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    rating_parameters = sa.table(
        "rating_parameters",
        sa.column("id", sa.String),
        sa.column("org_id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("scale_min", sa.Integer),
        sa.column("scale_max", sa.Integer),
        sa.column("is_active", sa.Boolean),
        sa.column("sort_order", sa.Integer),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    organizations = sa.table("organizations", sa.column("id", sa.String))

    bind = op.get_bind()
    org_ids = [row[0] for row in bind.execute(sa.select(organizations.c.id))]
    now = datetime.now(UTC)

    category_rows = [
        {
            "id": str(uuid.uuid4()), "org_id": org_id, "name": name, "description": description,
            "is_active": True, "is_default": is_default, "sort_order": idx,
            "created_at": now, "updated_at": now,
        }
        for org_id in org_ids
        for idx, (name, description, is_default) in enumerate(DEFAULT_CATEGORIES)
    ]
    if category_rows:
        op.bulk_insert(call_categories, category_rows)

    parameter_rows = [
        {
            "id": str(uuid.uuid4()), "org_id": org_id, "name": name, "description": description,
            "scale_min": scale_min, "scale_max": scale_max, "is_active": True, "sort_order": idx,
            "created_at": now, "updated_at": now,
        }
        for org_id in org_ids
        for idx, (name, description, scale_min, scale_max) in enumerate(DEFAULT_RATING_PARAMETERS)
    ]
    if parameter_rows:
        op.bulk_insert(rating_parameters, parameter_rows)


def downgrade() -> None:
    with op.batch_alter_table("analyses", schema=None) as batch_op:
        batch_op.drop_constraint("fk_analyses_category_id", type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_analyses_category_id"))
        batch_op.drop_column("custom_ratings")
        batch_op.drop_column("category_confidence")
        batch_op.drop_column("category_name")
        batch_op.drop_column("category_id")

    with op.batch_alter_table("leads", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_leads_org_id"))
        batch_op.drop_index("ix_leads_org_category_created")
        batch_op.drop_index(batch_op.f("ix_leads_call_id"))
        batch_op.drop_index(batch_op.f("ix_leads_agent_id"))
    op.drop_table("leads")

    with op.batch_alter_table("rating_parameters", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_rating_parameters_org_id"))
        batch_op.drop_index("ix_rating_parameters_org_active")
        batch_op.drop_index(batch_op.f("ix_rating_parameters_created_by_user_id"))
    op.drop_table("rating_parameters")

    with op.batch_alter_table("call_categories", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_call_categories_org_id"))
        batch_op.drop_index("ix_call_categories_org_active")
        batch_op.drop_index(batch_op.f("ix_call_categories_created_by_user_id"))
    op.drop_table("call_categories")
