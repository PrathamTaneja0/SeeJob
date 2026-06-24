"""ATS compatibility critic — keyword coverage and format checks."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

_HEADING_RE = re.compile(r"^#{1,6}\s+\S", re.MULTILINE)
_WORD_RE = re.compile(r"[a-z][a-z0-9+#.-]{1,}")


def _normalize_token(token: str) -> str:
    return token.strip(".,;:!?\"'()[]")

_STOPWORDS = frozenset(
    {
        "the",
        "and",
        "for",
        "with",
        "this",
        "that",
        "from",
        "will",
        "your",
        "our",
        "you",
        "are",
        "have",
        "has",
        "been",
        "was",
        "were",
        "about",
        "into",
        "their",
        "they",
        "them",
        "such",
        "able",
        "work",
        "role",
        "team",
        "using",
        "use",
        "used",
        "all",
        "any",
        "can",
        "may",
        "not",
        "but",
        "who",
        "what",
        "when",
        "where",
        "how",
        "job",
        "jobs",
        "company",
        "experience",
        "years",
        "year",
    }
)

_CHARS_PER_PAGE = 3000
_MIN_PAGES = 0.5
_MAX_PAGES = 2.5


@dataclass
class CriticIssue:
    """Single ATS critique finding."""

    code: str
    message: str
    severity: str = "warning"


@dataclass
class CriticResult:
    """Outcome of ATS critique for one document."""

    score: float
    passed: bool
    issues: list[CriticIssue] = field(default_factory=list)
    keyword_coverage: float = 0.0
    matched_keywords: list[str] = field(default_factory=list)
    missing_keywords: list[str] = field(default_factory=list)

    def to_report_json(self) -> str:
        """Serialize critic report for storage."""
        return json.dumps(
            {
                "score": round(self.score, 4),
                "passed": self.passed,
                "keyword_coverage": round(self.keyword_coverage, 4),
                "matched_keywords": self.matched_keywords[:30],
                "missing_keywords": self.missing_keywords[:30],
                "issues": [
                    {"code": i.code, "message": i.message, "severity": i.severity}
                    for i in self.issues
                ],
            }
        )

    @property
    def revision_notes(self) -> str:
        """Human-readable notes for LLM revision."""
        lines = [f"- {issue.message}" for issue in self.issues]
        if self.missing_keywords:
            lines.append(
                "- Integrate these JD keywords where truthful: "
                + ", ".join(self.missing_keywords[:15])
            )
        return "\n".join(lines) if lines else "Improve keyword alignment with the job description."


def extract_jd_keywords(jd_text: str, *, max_keywords: int = 40) -> list[str]:
    """Extract significant keywords from a job description."""
    if not jd_text.strip():
        return []

    counts: dict[str, int] = {}
    for raw in _WORD_RE.findall(jd_text.lower()):
        token = _normalize_token(raw)
        if token in _STOPWORDS or len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1

    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [word for word, _ in ranked[:max_keywords]]


def critique_document(
    markdown_content: str,
    *,
    jd_text: str,
    doc_type: str,
    min_score: float,
) -> CriticResult:
    """Score a document for ATS compatibility."""
    issues: list[CriticIssue] = []
    content_lower = markdown_content.lower()

    keywords = extract_jd_keywords(jd_text)
    content_tokens = {_normalize_token(t) for t in _WORD_RE.findall(content_lower)}
    matched = [kw for kw in keywords if kw in content_tokens]
    missing = [kw for kw in keywords if kw not in matched]
    keyword_coverage = (len(matched) / len(keywords)) if keywords else 1.0

    if keyword_coverage < 0.35 and keywords:
        issues.append(
            CriticIssue(
                code="low_keyword_coverage",
                message=f"Low keyword coverage ({keyword_coverage:.0%}) vs job description",
                severity="error",
            )
        )

    if not _HEADING_RE.search(markdown_content):
        issues.append(
            CriticIssue(
                code="missing_headings",
                message="Document lacks Markdown headings (use ## Section)",
                severity="error",
            )
        )

    char_count = len(markdown_content)
    page_equiv = char_count / _CHARS_PER_PAGE
    if page_equiv > _MAX_PAGES:
        issues.append(
            CriticIssue(
                code="too_long",
                message=f"Document may exceed {_MAX_PAGES:.0f} pages (~{page_equiv:.1f} pages)",
                severity="warning",
            )
        )
    if page_equiv < _MIN_PAGES and doc_type == "cv":
        issues.append(
            CriticIssue(
                code="too_short",
                message="CV appears shorter than half a page",
                severity="warning",
            )
        )

    if "|" in markdown_content and "---" in markdown_content:
        issues.append(
            CriticIssue(
                code="tables_detected",
                message="Avoid tables for ATS compatibility",
                severity="warning",
            )
        )

    format_score = 1.0
    for issue in issues:
        if issue.severity == "error":
            format_score -= 0.25
        else:
            format_score -= 0.1
    format_score = max(0.0, format_score)

    score = 0.6 * keyword_coverage + 0.4 * format_score
    has_errors = any(i.severity == "error" for i in issues)
    passed = score >= min_score and not has_errors

    if doc_type == "cover_letter" and keyword_coverage >= 0.25 and not has_errors:
        passed = passed or score >= min_score * 0.9

    return CriticResult(
        score=round(score, 4),
        passed=passed,
        issues=issues,
        keyword_coverage=keyword_coverage,
        matched_keywords=matched,
        missing_keywords=missing,
    )
