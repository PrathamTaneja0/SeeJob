"""Add job sourcing fields — url_hash, match_rationale, is_remote, rss feeds."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003_job_sourcing"
down_revision: Union[str, None] = "002_unique_application"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add deduplication hash, scoring rationale, remote flag, and RSS feed config."""
    op.add_column("jobs", sa.Column("url_hash", sa.String(length=64), nullable=True))
    op.add_column("jobs", sa.Column("match_rationale", sa.Text(), nullable=True))
    op.add_column(
        "jobs",
        sa.Column("is_remote", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_jobs_url_hash", "jobs", ["url_hash"], unique=True)

    op.add_column("policy_config", sa.Column("rss_feeds_json", sa.Text(), nullable=True))


def downgrade() -> None:
    """Remove sourcing-related columns."""
    op.drop_column("policy_config", "rss_feeds_json")
    op.drop_index("ix_jobs_url_hash", table_name="jobs")
    op.drop_column("jobs", "is_remote")
    op.drop_column("jobs", "match_rationale")
    op.drop_column("jobs", "url_hash")
