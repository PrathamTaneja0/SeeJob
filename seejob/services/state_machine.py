"""Application state machine — valid transitions and enforcement."""

from seejob.models.application import ApplicationStatus


class InvalidTransitionError(ValueError):
    """Raised when an application status transition is not allowed."""

    def __init__(self, current: ApplicationStatus, target: ApplicationStatus) -> None:
        self.current = current
        self.target = target
        valid = get_valid_transitions(current)
        super().__init__(
            f"Cannot transition from '{current.value}' to '{target.value}'. "
            f"Valid targets: {[s.value for s in valid]}"
        )


VALID_TRANSITIONS: dict[ApplicationStatus, frozenset[ApplicationStatus]] = {
    ApplicationStatus.DISCOVERED: frozenset({ApplicationStatus.SCORED, ApplicationStatus.FAILED}),
    ApplicationStatus.SCORED: frozenset(
        {ApplicationStatus.PENDING_APPROVAL, ApplicationStatus.FAILED}
    ),
    ApplicationStatus.PENDING_APPROVAL: frozenset(
        {ApplicationStatus.GENERATING_DOCS, ApplicationStatus.FAILED}
    ),
    ApplicationStatus.GENERATING_DOCS: frozenset(
        {ApplicationStatus.DOCS_READY, ApplicationStatus.FAILED}
    ),
    ApplicationStatus.DOCS_READY: frozenset(
        {
            ApplicationStatus.AUTH_REQUIRED,
            ApplicationStatus.FILLING,
            ApplicationStatus.PENDING_APPROVAL,
            ApplicationStatus.FAILED,
        }
    ),
    ApplicationStatus.AUTH_REQUIRED: frozenset(
        {
            ApplicationStatus.FILLING,
            ApplicationStatus.NEEDS_MANUAL,
            ApplicationStatus.FAILED,
        }
    ),
    ApplicationStatus.FILLING: frozenset(
        {
            ApplicationStatus.SUBMITTED,
            ApplicationStatus.NEEDS_MANUAL,
            ApplicationStatus.AUTH_REQUIRED,
            ApplicationStatus.FAILED,
        }
    ),
    ApplicationStatus.NEEDS_MANUAL: frozenset(
        {
            ApplicationStatus.FILLING,
            ApplicationStatus.AUTH_REQUIRED,
            ApplicationStatus.FAILED,
        }
    ),
    ApplicationStatus.FAILED: frozenset(
        {ApplicationStatus.DISCOVERED, ApplicationStatus.SCORED, ApplicationStatus.PENDING_APPROVAL}
    ),
    ApplicationStatus.SUBMITTED: frozenset(),
}

TERMINAL_STATUSES: frozenset[ApplicationStatus] = frozenset({ApplicationStatus.SUBMITTED})


def get_valid_transitions(current: ApplicationStatus) -> frozenset[ApplicationStatus]:
    """Return allowed target statuses from the current status."""
    return VALID_TRANSITIONS.get(current, frozenset())


def can_transition(current: ApplicationStatus, target: ApplicationStatus) -> bool:
    """Return True if the transition from current to target is valid."""
    if current == target:
        return True
    return target in get_valid_transitions(current)


def transition(current: ApplicationStatus, target: ApplicationStatus) -> ApplicationStatus:
    """Validate and return the target status, raising if invalid."""
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)
    return target
