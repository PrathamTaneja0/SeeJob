"""Add unique constraint on applications (person_id, job_id)."""

from typing import Sequence, Union

from alembic import op

revision: str = "002_unique_application"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Prevent duplicate applications for the same person and job."""
    with op.batch_alter_table("applications") as batch_op:
        batch_op.create_unique_constraint(
            "uq_application_person_job",
            ["person_id", "job_id"],
        )


def downgrade() -> None:
    """Remove the person/job uniqueness constraint."""
    with op.batch_alter_table("applications") as batch_op:
        batch_op.drop_constraint("uq_application_person_job", type_="unique")
