"""Agent orchestration interfaces — planner layer (Phase 1+)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentTaskType(str, Enum):
    """Types of orchestrator tasks."""

    SOURCE_JOBS = "source_jobs"
    SCORE_JOB = "score_job"
    GENERATE_DOCUMENTS = "generate_documents"
    CRITIQUE_DOCUMENTS = "critique_documents"
    FILL_APPLICATION = "fill_application"
    ANSWER_SCREENING = "answer_screening"


@dataclass
class TruthfulnessConstraint:
    """Guardrails for document generation — no fabricated experience."""

    allow_inference: bool = False
    max_embellishment: str = "none"
    require_source_citation: bool = True
    blocked_claims: list[str] = field(default_factory=list)


@dataclass
class AgentContext:
    """Context passed to agent tasks."""

    person_id: int
    application_id: int | None = None
    job_id: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AgentResult:
    """Result from an agent task execution."""

    success: bool
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    requires_approval: bool = False
    approval_reason: str | None = None


class DocumentGenerator(ABC):
    """Interface for LLM-powered document generation (Phase 1+)."""

    @abstractmethod
    async def generate_cv(
        self,
        context: AgentContext,
        constraints: TruthfulnessConstraint,
    ) -> AgentResult:
        """Generate a tailored CV from verified profile data only."""

    @abstractmethod
    async def generate_cover_letter(
        self,
        context: AgentContext,
        constraints: TruthfulnessConstraint,
    ) -> AgentResult:
        """Generate a cover letter with truthfulness guard."""

    @abstractmethod
    async def critique_documents(self, context: AgentContext) -> AgentResult:
        """Run ATS compatibility and truthfulness critique."""


class ScreeningAnswerer(ABC):
    """Interface for behavioral question answering with Q&A bank cache."""

    @abstractmethod
    async def answer_question(
        self,
        context: AgentContext,
        question: str,
        *,
        use_cache: bool = True,
    ) -> AgentResult:
        """Answer a screening question, preferring cached Q&A bank hits."""


class JobScorer(ABC):
    """Interface for job fit scoring."""

    @abstractmethod
    async def score_job(self, context: AgentContext, jd_text: str) -> AgentResult:
        """Score job fit against person profile."""


class Orchestrator(ABC):
    """Top-level orchestrator coordinating workers and approval gates."""

    @abstractmethod
    async def run_pipeline_step(self, application_id: int) -> AgentResult:
        """Advance one application through the next pipeline step."""

    @abstractmethod
    async def request_approval(self, application_id: int, gate: str) -> AgentResult:
        """Pause at doc preview or submit approval gate."""
