"""Initial SeeJob schema — all Phase 0 models."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables."""
    op.create_table(
        "persons",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("phone", sa.String(length=50), nullable=True),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("headline", sa.String(length=500), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("linkedin_url", sa.String(length=500), nullable=True),
        sa.Column("github_url", sa.String(length=500), nullable=True),
        sa.Column("portfolio_url", sa.String(length=500), nullable=True),
        sa.Column(
            "work_authorization",
            sa.Enum(
                "citizen",
                "permanent_resident",
                "work_visa",
                "student_visa",
                "requires_sponsorship",
                "other",
                name="work_authorization",
            ),
            nullable=False,
        ),
        sa.Column("willing_to_relocate", sa.Boolean(), nullable=False),
        sa.Column("remote_preference", sa.String(length=50), nullable=True),
        sa.Column("desired_roles", sa.Text(), nullable=True),
        sa.Column("salary_min", sa.Integer(), nullable=True),
        sa.Column("salary_currency", sa.String(length=3), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("ix_persons_email", "persons", ["email"])

    op.create_table(
        "experiences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_experiences_person_id", "experiences", ["person_id"])

    op.create_table(
        "education",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("institution", sa.String(length=255), nullable=False),
        sa.Column("degree", sa.String(length=255), nullable=True),
        sa.Column("field_of_study", sa.String(length=255), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=True),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("gpa", sa.String(length=20), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_education_person_id", "education", ["person_id"])

    op.create_table(
        "skills",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("level", sa.String(length=50), nullable=True),
        sa.Column("years", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skills_person_id", "skills", ["person_id"])

    op.create_table(
        "screening_answers",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_hash", sa.String(length=64), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("source", sa.String(length=100), nullable=True),
        sa.Column("times_used", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("person_id", "question_hash", name="uq_person_question_hash"),
    )
    op.create_index("ix_screening_answers_person_id", "screening_answers", ["person_id"])
    op.create_index("ix_screening_answers_question_hash", "screening_answers", ["question_hash"])

    op.create_table(
        "site_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("platform", sa.String(length=100), nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=True),
        sa.Column("username_encrypted", sa.Text(), nullable=False),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("session_data_encrypted", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_site_accounts_person_id", "site_accounts", ["person_id"])
    op.create_index("ix_site_accounts_platform", "site_accounts", ["platform"])

    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("company", sa.String(length=255), nullable=False),
        sa.Column("location", sa.String(length=255), nullable=True),
        sa.Column("jd_text", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=100), nullable=False),
        sa.Column("fit_score", sa.Float(), nullable=True),
        sa.Column(
            "status",
            sa.Enum("new", "reviewed", "archived", "applied", "rejected", name="job_status"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("url"),
    )
    op.create_index("ix_jobs_url", "jobs", ["url"])
    op.create_index("ix_jobs_company", "jobs", ["company"])
    op.create_index("ix_jobs_source", "jobs", ["source"])
    op.create_index("ix_jobs_status", "jobs", ["status"])

    op.create_table(
        "applications",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("person_id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "discovered",
                "scored",
                "pending_approval",
                "generating_docs",
                "docs_ready",
                "auth_required",
                "filling",
                "submitted",
                "failed",
                "needs_manual",
                name="application_status",
            ),
            nullable=False,
        ),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("platform", sa.String(length=100), nullable=True),
        sa.Column("submitted_at", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["person_id"], ["persons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_applications_person_id", "applications", ["person_id"])
    op.create_index("ix_applications_job_id", "applications", ["job_id"])
    op.create_index("ix_applications_status", "applications", ["status"])

    op.create_table(
        "generated_documents",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("application_id", sa.Integer(), nullable=False),
        sa.Column(
            "doc_type",
            sa.Enum("cv", "cover_letter", "other", name="document_type"),
            nullable=False,
        ),
        sa.Column("markdown_content", sa.Text(), nullable=False),
        sa.Column("pdf_path", sa.String(length=1000), nullable=True),
        sa.Column("ats_score", sa.Float(), nullable=True),
        sa.Column("critic_report", sa.Text(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.ForeignKeyConstraint(["application_id"], ["applications.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_documents_application_id", "generated_documents", ["application_id"])

    op.create_table(
        "ats_learnings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("domain", sa.String(length=255), nullable=False),
        sa.Column("procedure_key", sa.String(length=255), nullable=False),
        sa.Column("procedure_data", sa.Text(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain", "procedure_key", name="uq_domain_procedure"),
    )
    op.create_index("ix_ats_learnings_domain", "ats_learnings", ["domain"])

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("worker_name", sa.String(length=100), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "running", "completed", "failed", "cancelled", name="agent_run_status"),
            nullable=False,
        ),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.String(length=50), nullable=True),
        sa.Column("finished_at", sa.String(length=50), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_runs_worker_name", "agent_runs", ["worker_name"])
    op.create_index("ix_agent_runs_status", "agent_runs", ["status"])

    op.create_table(
        "policy_config",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("auto_apply", sa.Boolean(), nullable=False),
        sa.Column("require_doc_approval", sa.Boolean(), nullable=False),
        sa.Column("require_submit_approval", sa.Boolean(), nullable=False),
        sa.Column("min_fit_score", sa.Float(), nullable=False),
        sa.Column("daily_apply_limit", sa.Integer(), nullable=False),
        sa.Column("rate_limits_json", sa.Text(), nullable=False),
        sa.Column("job_filters_json", sa.Text(), nullable=True),
        sa.Column("blocked_companies_json", sa.Text(), nullable=True),
        sa.Column("blocked_keywords_json", sa.Text(), nullable=True),
        sa.Column("sourcing_enabled", sa.Boolean(), nullable=False),
        sa.Column("sourcing_schedule", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("(CURRENT_TIMESTAMP)"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    """Drop all tables."""
    op.drop_table("policy_config")
    op.drop_table("agent_runs")
    op.drop_table("ats_learnings")
    op.drop_table("generated_documents")
    op.drop_table("applications")
    op.drop_table("jobs")
    op.drop_table("site_accounts")
    op.drop_table("screening_answers")
    op.drop_table("skills")
    op.drop_table("education")
    op.drop_table("experiences")
    op.drop_table("persons")
    op.execute("DROP TYPE IF EXISTS agent_run_status")
    op.execute("DROP TYPE IF EXISTS document_type")
    op.execute("DROP TYPE IF EXISTS application_status")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS work_authorization")
