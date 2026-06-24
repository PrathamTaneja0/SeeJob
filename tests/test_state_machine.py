"""Tests for application state machine transitions."""

import pytest

from seejob.models.application import ApplicationStatus
from seejob.services.state_machine import (
    TERMINAL_STATUSES,
    InvalidTransitionError,
    can_transition,
    get_valid_transitions,
    transition,
)


class TestValidTransitions:
    """Verify allowed transition paths."""

    @pytest.mark.parametrize(
        ("current", "target", "expected"),
        [
            (ApplicationStatus.DISCOVERED, ApplicationStatus.SCORED, True),
            (ApplicationStatus.SCORED, ApplicationStatus.PENDING_APPROVAL, True),
            (ApplicationStatus.PENDING_APPROVAL, ApplicationStatus.GENERATING_DOCS, True),
            (ApplicationStatus.GENERATING_DOCS, ApplicationStatus.DOCS_READY, True),
            (ApplicationStatus.DOCS_READY, ApplicationStatus.FILLING, True),
            (ApplicationStatus.DOCS_READY, ApplicationStatus.AUTH_REQUIRED, True),
            (ApplicationStatus.FILLING, ApplicationStatus.SUBMITTED, True),
            (ApplicationStatus.FILLING, ApplicationStatus.NEEDS_MANUAL, True),
            (ApplicationStatus.NEEDS_MANUAL, ApplicationStatus.FILLING, True),
            (ApplicationStatus.FAILED, ApplicationStatus.DISCOVERED, True),
            (ApplicationStatus.SUBMITTED, ApplicationStatus.FAILED, False),
            (ApplicationStatus.DISCOVERED, ApplicationStatus.SUBMITTED, False),
            (ApplicationStatus.SCORED, ApplicationStatus.FILLING, False),
        ],
    )
    def test_can_transition(
        self,
        current: ApplicationStatus,
        target: ApplicationStatus,
        expected: bool,
    ) -> None:
        assert can_transition(current, target) is expected

    def test_same_status_always_allowed(self) -> None:
        for status in ApplicationStatus:
            assert can_transition(status, status) is True

    def test_submitted_is_terminal(self) -> None:
        assert ApplicationStatus.SUBMITTED in TERMINAL_STATUSES
        assert get_valid_transitions(ApplicationStatus.SUBMITTED) == frozenset()

    def test_transition_success(self) -> None:
        result = transition(ApplicationStatus.DISCOVERED, ApplicationStatus.SCORED)
        assert result == ApplicationStatus.SCORED

    def test_transition_raises_on_invalid(self) -> None:
        with pytest.raises(InvalidTransitionError) as exc_info:
            transition(ApplicationStatus.DISCOVERED, ApplicationStatus.SUBMITTED)
        assert exc_info.value.current == ApplicationStatus.DISCOVERED
        assert exc_info.value.target == ApplicationStatus.SUBMITTED

    def test_full_happy_path(self) -> None:
        path = [
            ApplicationStatus.DISCOVERED,
            ApplicationStatus.SCORED,
            ApplicationStatus.PENDING_APPROVAL,
            ApplicationStatus.GENERATING_DOCS,
            ApplicationStatus.DOCS_READY,
            ApplicationStatus.FILLING,
            ApplicationStatus.SUBMITTED,
        ]
        for current, target in zip(path, path[1:], strict=False):
            assert can_transition(current, target)
