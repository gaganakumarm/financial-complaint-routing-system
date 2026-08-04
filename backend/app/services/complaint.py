"""Transaction-neutral complaint lifecycle business logic."""

from collections.abc import Sequence
from uuid import UUID, uuid4

from app.models import (
    Complaint,
    ComplaintChangeSource,
    ComplaintStatus,
    ComplaintStatusHistory,
    ComplaintUrgency,
    User,
)
from app.repositories import ComplaintRepository


class ComplaintServiceError(Exception):
    """Base exception for complaint service failures."""


class ComplaintNotFoundError(ComplaintServiceError):
    """Raised when a complaint cannot be found."""


class ComplaintAccessDeniedError(ComplaintServiceError):
    """Raised when a user cannot perform a complaint operation."""


class InvalidComplaintDataError(ComplaintServiceError):
    """Raised when complaint input is invalid."""


class InvalidComplaintStatusTransitionError(ComplaintServiceError):
    """Raised when a complaint status transition is not allowed."""


class InvalidComplaintRoutingError(ComplaintServiceError):
    """Raised when final routing input or state is invalid."""


_DESCRIPTION_MAX_LENGTH = 10_000
_HISTORY_REASON_MAX_LENGTH = 2_000

_ALLOWED_TRANSITIONS: dict[ComplaintStatus, frozenset[ComplaintStatus]] = {
    ComplaintStatus.SUBMITTED: frozenset(
        {
            ComplaintStatus.PREDICTION_PENDING,
            ComplaintStatus.AWAITING_REVIEW,
            ComplaintStatus.CLOSED,
        }
    ),
    ComplaintStatus.PREDICTION_PENDING: frozenset(
        {
            ComplaintStatus.PREDICTION_COMPLETED,
            ComplaintStatus.PREDICTION_FAILED,
            ComplaintStatus.AWAITING_REVIEW,
        }
    ),
    ComplaintStatus.PREDICTION_COMPLETED: frozenset(
        {
            ComplaintStatus.AWAITING_REVIEW,
            ComplaintStatus.ROUTED,
            ComplaintStatus.CLOSED,
        }
    ),
    ComplaintStatus.PREDICTION_FAILED: frozenset(
        {ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.CLOSED}
    ),
    ComplaintStatus.AWAITING_REVIEW: frozenset(
        {
            ComplaintStatus.UNDER_REVIEW,
            ComplaintStatus.ROUTED,
            ComplaintStatus.CLOSED,
        }
    ),
    ComplaintStatus.UNDER_REVIEW: frozenset(
        {
            ComplaintStatus.AWAITING_REVIEW,
            ComplaintStatus.ROUTED,
            ComplaintStatus.CLOSED,
        }
    ),
    ComplaintStatus.ROUTED: frozenset({ComplaintStatus.CLOSED}),
    ComplaintStatus.CLOSED: frozenset(),
}


def _normalize_required_text(
    value: str,
    *,
    field_name: str,
    minimum_length: int,
    maximum_length: int,
) -> str:
    if not isinstance(value, str):
        raise InvalidComplaintDataError(f"{field_name} is invalid.")
    normalized = value.strip()
    if not minimum_length <= len(normalized) <= maximum_length:
        raise InvalidComplaintDataError(f"{field_name} is invalid.")
    return normalized


def _normalize_optional_text(
    value: str | None,
    *,
    field_name: str,
    maximum_length: int,
) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidComplaintDataError(f"{field_name} is invalid.")
    normalized = value.strip()
    if not normalized:
        return None
    if len(normalized) > maximum_length:
        raise InvalidComplaintDataError(f"{field_name} is invalid.")
    return normalized


def _generate_reference_number() -> str:
    """Generate an opaque, non-sequential complaint reference."""
    return f"FCR-{uuid4().hex[:12].upper()}"


def _validate_transition(
    current_status: ComplaintStatus,
    new_status: ComplaintStatus,
) -> None:
    if not isinstance(current_status, ComplaintStatus) or not isinstance(
        new_status, ComplaintStatus
    ):
        raise InvalidComplaintStatusTransitionError(
            "Complaint status transition is not allowed."
        )
    if new_status not in _ALLOWED_TRANSITIONS[current_status]:
        raise InvalidComplaintStatusTransitionError(
            "Complaint status transition is not allowed."
        )


class ComplaintService:
    """Coordinate complaint lifecycle persistence without owning transactions."""

    def __init__(self, complaint_repository: ComplaintRepository) -> None:
        self._complaint_repository = complaint_repository

    def _persist_history(self, history: ComplaintStatusHistory) -> None:
        self._complaint_repository.session.add(history)

    async def create_complaint(
        self,
        *,
        customer: User,
        title: str,
        description: str,
    ) -> Complaint:
        customer_id = customer.__dict__.get("id")
        if customer_id is None:
            raise InvalidComplaintDataError("Customer data is invalid.")
        if not customer.is_active:
            raise ComplaintAccessDeniedError("Complaint access is denied.")
        loaded_role = customer.__dict__.get("role")
        if loaded_role is not None:
            try:
                role_name = loaded_role.name.strip().lower()
            except AttributeError:
                raise ComplaintAccessDeniedError("Complaint access is denied.") from None
            if role_name != "customer":
                raise ComplaintAccessDeniedError("Complaint access is denied.")
        normalized_title = _normalize_required_text(
            title,
            field_name="Complaint title",
            minimum_length=1,
            maximum_length=200,
        )
        normalized_description = _normalize_required_text(
            description,
            field_name="Complaint description",
            minimum_length=1,
            maximum_length=_DESCRIPTION_MAX_LENGTH,
        )
        complaint = Complaint(
            reference_number=_generate_reference_number(),
            customer_id=customer_id,
            title=normalized_title,
            description=normalized_description,
            current_status=ComplaintStatus.SUBMITTED,
            final_category_id=None,
            final_department_id=None,
            final_urgency=None,
        )
        await self._complaint_repository.add(complaint)
        await self._complaint_repository.flush()
        history = ComplaintStatusHistory(
            complaint=complaint,
            complaint_id=complaint.id,
            previous_status=None,
            new_status=ComplaintStatus.SUBMITTED,
            changed_by_user_id=customer_id,
            change_source=ComplaintChangeSource.CUSTOMER,
            reason=None,
        )
        self._persist_history(history)
        await self._complaint_repository.flush()
        return await self._complaint_repository.refresh(complaint)

    async def get_complaint(self, complaint_id: UUID) -> Complaint:
        complaint = await self._complaint_repository.get_by_id(complaint_id)
        if complaint is None:
            raise ComplaintNotFoundError("Complaint was not found.")
        return complaint

    async def get_customer_complaint(
        self,
        *,
        complaint_id: UUID,
        customer_id: UUID,
    ) -> Complaint:
        complaint = await self.get_complaint(complaint_id)
        if complaint.customer_id != customer_id:
            raise ComplaintAccessDeniedError("Complaint access is denied.")
        return complaint

    async def list_customer_complaints(
        self,
        *,
        customer_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Complaint]:
        return await self._complaint_repository.list_for_customer(
            customer_id,
            offset=offset,
            limit=limit,
        )

    async def list_review_queue(
        self,
        *,
        statuses: Sequence[ComplaintStatus] | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Complaint]:
        return await self._complaint_repository.list_review_queue(
            statuses=statuses,
            offset=offset,
            limit=limit,
        )

    async def transition_status(
        self,
        *,
        complaint: Complaint,
        new_status: ComplaintStatus,
        changed_by_user_id: UUID | None,
        source: ComplaintChangeSource,
        notes: str | None = None,
    ) -> Complaint:
        previous_status = complaint.current_status
        _validate_transition(previous_status, new_status)
        if complaint.__dict__.get("id") is None:
            raise InvalidComplaintDataError("Complaint data is invalid.")
        if not isinstance(source, ComplaintChangeSource):
            raise InvalidComplaintDataError("Complaint change source is invalid.")
        normalized_notes = _normalize_optional_text(
            notes,
            field_name="Complaint status notes",
            maximum_length=_HISTORY_REASON_MAX_LENGTH,
        )

        complaint.current_status = new_status
        history = ComplaintStatusHistory(
            complaint=complaint,
            complaint_id=complaint.id,
            previous_status=previous_status,
            new_status=new_status,
            changed_by_user_id=changed_by_user_id,
            change_source=source,
            reason=normalized_notes,
        )
        self._persist_history(history)
        await self._complaint_repository.flush()
        return await self._complaint_repository.refresh(complaint)

    async def assign_routing(
        self,
        *,
        complaint: Complaint,
        category_id: UUID,
        department_id: UUID,
        urgency: ComplaintUrgency,
        changed_by_user_id: UUID,
        source: ComplaintChangeSource,
        notes: str | None = None,
    ) -> Complaint:
        if complaint.current_status == ComplaintStatus.CLOSED:
            raise InvalidComplaintRoutingError("Complaint routing is invalid.")
        if not isinstance(complaint.__dict__.get("id"), UUID):
            raise InvalidComplaintRoutingError("Complaint routing is invalid.")
        if not isinstance(category_id, UUID) or not isinstance(department_id, UUID):
            raise InvalidComplaintRoutingError("Complaint routing is invalid.")
        if not isinstance(changed_by_user_id, UUID):
            raise InvalidComplaintRoutingError("Complaint routing is invalid.")
        if not isinstance(urgency, ComplaintUrgency):
            raise InvalidComplaintRoutingError("Complaint routing is invalid.")
        if not isinstance(source, ComplaintChangeSource):
            raise InvalidComplaintRoutingError("Complaint routing is invalid.")
        try:
            _validate_transition(complaint.current_status, ComplaintStatus.ROUTED)
            _normalize_optional_text(
                notes,
                field_name="Complaint routing notes",
                maximum_length=_HISTORY_REASON_MAX_LENGTH,
            )
        except (
            InvalidComplaintDataError,
            InvalidComplaintStatusTransitionError,
        ):
            raise InvalidComplaintRoutingError("Complaint routing is invalid.") from None

        complaint.final_category_id = category_id
        complaint.final_department_id = department_id
        complaint.final_urgency = urgency
        return await self.transition_status(
            complaint=complaint,
            new_status=ComplaintStatus.ROUTED,
            changed_by_user_id=changed_by_user_id,
            source=source,
            notes=notes,
        )
