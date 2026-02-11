"""add llm model registry

Revision ID: 9a3fb1158c2d
Revises: f4d2b649e93a
Create Date: 2026-02-11 21:00:00.000000

"""

from __future__ import annotations

import sqlalchemy as sa
import sqlmodel
from alembic import op

# revision identifiers, used by Alembic.
revision = "9a3fb1158c2d"
down_revision = "f4d2b649e93a"
branch_labels = None
depends_on = None


def _has_index(inspector: sa.Inspector, table: str, index_name: str) -> bool:
    return any(item.get("name") == index_name for item in inspector.get_indexes(table))


def _has_unique(
    inspector: sa.Inspector,
    table: str,
    *,
    name: str | None = None,
    columns: tuple[str, ...] | None = None,
) -> bool:
    unique_constraints = inspector.get_unique_constraints(table)
    for item in unique_constraints:
        if name and item.get("name") == name:
            return True
        if columns and tuple(item.get("column_names") or ()) == columns:
            return True
    return False


def _column_names(inspector: sa.Inspector, table: str) -> set[str]:
    return {item["name"] for item in inspector.get_columns(table)}


def _has_foreign_key(
    inspector: sa.Inspector,
    table: str,
    *,
    constrained_columns: tuple[str, ...],
    referred_table: str,
) -> bool:
    for item in inspector.get_foreign_keys(table):
        if tuple(item.get("constrained_columns") or ()) != constrained_columns:
            continue
        if item.get("referred_table") != referred_table:
            continue
        return True
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("llm_provider_auth"):
        op.create_table(
            "llm_provider_auth",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("gateway_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("config_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("secret", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["gateway_id"], ["gateways.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "gateway_id",
                "provider",
                "config_path",
                name="uq_llm_provider_auth_gateway_provider_path",
            ),
        )
        inspector = sa.inspect(bind)
    else:
        existing_columns = _column_names(inspector, "llm_provider_auth")
        if "config_path" not in existing_columns:
            op.add_column(
                "llm_provider_auth",
                sa.Column(
                    "config_path",
                    sqlmodel.sql.sqltypes.AutoString(),
                    nullable=False,
                    server_default="providers.openai.apiKey",
                ),
            )
            op.alter_column("llm_provider_auth", "config_path", server_default=None)
            inspector = sa.inspect(bind)
        if not _has_unique(
            inspector,
            "llm_provider_auth",
            name="uq_llm_provider_auth_gateway_provider_path",
            columns=("gateway_id", "provider", "config_path"),
        ):
            op.create_unique_constraint(
                "uq_llm_provider_auth_gateway_provider_path",
                "llm_provider_auth",
                ["gateway_id", "provider", "config_path"],
            )
            inspector = sa.inspect(bind)

    if not _has_index(inspector, "llm_provider_auth", op.f("ix_llm_provider_auth_gateway_id")):
        op.create_index(
            op.f("ix_llm_provider_auth_gateway_id"),
            "llm_provider_auth",
            ["gateway_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(
        inspector,
        "llm_provider_auth",
        op.f("ix_llm_provider_auth_organization_id"),
    ):
        op.create_index(
            op.f("ix_llm_provider_auth_organization_id"),
            "llm_provider_auth",
            ["organization_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(inspector, "llm_provider_auth", op.f("ix_llm_provider_auth_provider")):
        op.create_index(
            op.f("ix_llm_provider_auth_provider"),
            "llm_provider_auth",
            ["provider"],
            unique=False,
        )
        inspector = sa.inspect(bind)

    if not inspector.has_table("llm_models"):
        op.create_table(
            "llm_models",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("organization_id", sa.Uuid(), nullable=False),
            sa.Column("gateway_id", sa.Uuid(), nullable=False),
            sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("model_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("settings", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["gateway_id"], ["gateways.id"]),
            sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"]),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("gateway_id", "model_id", name="uq_llm_models_gateway_model_id"),
        )
        inspector = sa.inspect(bind)
    elif not _has_unique(
        inspector,
        "llm_models",
        name="uq_llm_models_gateway_model_id",
        columns=("gateway_id", "model_id"),
    ):
        op.create_unique_constraint(
            "uq_llm_models_gateway_model_id",
            "llm_models",
            ["gateway_id", "model_id"],
        )
        inspector = sa.inspect(bind)

    if not _has_index(inspector, "llm_models", op.f("ix_llm_models_gateway_id")):
        op.create_index(
            op.f("ix_llm_models_gateway_id"),
            "llm_models",
            ["gateway_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(inspector, "llm_models", op.f("ix_llm_models_model_id")):
        op.create_index(
            op.f("ix_llm_models_model_id"),
            "llm_models",
            ["model_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(inspector, "llm_models", op.f("ix_llm_models_organization_id")):
        op.create_index(
            op.f("ix_llm_models_organization_id"),
            "llm_models",
            ["organization_id"],
            unique=False,
        )
        inspector = sa.inspect(bind)
    if not _has_index(inspector, "llm_models", op.f("ix_llm_models_provider")):
        op.create_index(
            op.f("ix_llm_models_provider"),
            "llm_models",
            ["provider"],
            unique=False,
        )
        inspector = sa.inspect(bind)

    agent_columns = _column_names(inspector, "agents")
    if "primary_model_id" not in agent_columns:
        op.add_column("agents", sa.Column("primary_model_id", sa.Uuid(), nullable=True))
        inspector = sa.inspect(bind)
    if "fallback_model_ids" not in agent_columns:
        op.add_column("agents", sa.Column("fallback_model_ids", sa.JSON(), nullable=True))
        inspector = sa.inspect(bind)
    if not _has_index(inspector, "agents", op.f("ix_agents_primary_model_id")):
        op.create_index(op.f("ix_agents_primary_model_id"), "agents", ["primary_model_id"], unique=False)
        inspector = sa.inspect(bind)
    if not _has_foreign_key(
        inspector,
        "agents",
        constrained_columns=("primary_model_id",),
        referred_table="llm_models",
    ):
        op.create_foreign_key(
            "fk_agents_primary_model_id_llm_models",
            "agents",
            "llm_models",
            ["primary_model_id"],
            ["id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("agents"):
        for fk in inspector.get_foreign_keys("agents"):
            if tuple(fk.get("constrained_columns") or ()) != ("primary_model_id",):
                continue
            if fk.get("referred_table") != "llm_models":
                continue
            fk_name = fk.get("name")
            if fk_name:
                op.drop_constraint(fk_name, "agents", type_="foreignkey")
        inspector = sa.inspect(bind)
        if _has_index(inspector, "agents", op.f("ix_agents_primary_model_id")):
            op.drop_index(op.f("ix_agents_primary_model_id"), table_name="agents")
        agent_columns = _column_names(inspector, "agents")
        if "fallback_model_ids" in agent_columns:
            op.drop_column("agents", "fallback_model_ids")
        if "primary_model_id" in agent_columns:
            op.drop_column("agents", "primary_model_id")

    inspector = sa.inspect(bind)
    if inspector.has_table("llm_models"):
        if _has_index(inspector, "llm_models", op.f("ix_llm_models_provider")):
            op.drop_index(op.f("ix_llm_models_provider"), table_name="llm_models")
        if _has_index(inspector, "llm_models", op.f("ix_llm_models_organization_id")):
            op.drop_index(op.f("ix_llm_models_organization_id"), table_name="llm_models")
        if _has_index(inspector, "llm_models", op.f("ix_llm_models_model_id")):
            op.drop_index(op.f("ix_llm_models_model_id"), table_name="llm_models")
        if _has_index(inspector, "llm_models", op.f("ix_llm_models_gateway_id")):
            op.drop_index(op.f("ix_llm_models_gateway_id"), table_name="llm_models")
        op.drop_table("llm_models")

    inspector = sa.inspect(bind)
    if inspector.has_table("llm_provider_auth"):
        if _has_index(inspector, "llm_provider_auth", op.f("ix_llm_provider_auth_provider")):
            op.drop_index(op.f("ix_llm_provider_auth_provider"), table_name="llm_provider_auth")
        if _has_index(
            inspector,
            "llm_provider_auth",
            op.f("ix_llm_provider_auth_organization_id"),
        ):
            op.drop_index(
                op.f("ix_llm_provider_auth_organization_id"),
                table_name="llm_provider_auth",
            )
        if _has_index(inspector, "llm_provider_auth", op.f("ix_llm_provider_auth_gateway_id")):
            op.drop_index(
                op.f("ix_llm_provider_auth_gateway_id"),
                table_name="llm_provider_auth",
            )
        op.drop_table("llm_provider_auth")
