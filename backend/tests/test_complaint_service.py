"""Tests for transaction-neutral complaint lifecycle services."""

import re
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

import app.services as services
from app.db.engine import get_engine
from app.db.session import get_session_factory
from app.models import (
    Complaint,
    ComplaintChangeSource,
    ComplaintStatus,
    ComplaintStatusHistory,
    ComplaintUrgency,
    Role,
    User,
)
from app.repositories import ComplaintRepository
from app.services import (
    AuthenticationError,
    AuthService,
    ComplaintAccessDeniedError,
    ComplaintNotFoundError,
    ComplaintService,
    ComplaintServiceError,
    InvalidComplaintDataError,
    InvalidComplaintRoutingError,
    InvalidComplaintStatusTransitionError,
)
from app.services.complaint import _generate_reference_number


def _repository() -> MagicMock:
    repository = MagicMock(spec=ComplaintRepository)
    repository.session = MagicMock()
    for method in (
        "add",
        "flush",
        "refresh",
        "get_by_id",
        "list_for_customer",
        "list_review_queue",
    ):
        setattr(repository, method, AsyncMock())
    repository.commit = AsyncMock()
    repository.rollback = AsyncMock()
    repository.begin = AsyncMock()
    return repository


def _user(*, role_name: str | None = "customer", active: bool = True) -> User:
    user = User(
        id=uuid4(),
        role_id=uuid4(),
        email="customer@example.com",
        password_hash="unused",
        full_name="Customer",
        is_active=active,
        email_verified=False,
    )
    if role_name is not None:
        user.role = Role(
            id=user.role_id,
            name=role_name,
            display_name="Role",
            is_active=True,
        )
    return user


def _complaint(status: ComplaintStatus = ComplaintStatus.SUBMITTED) -> Complaint:
    return Complaint(
        id=uuid4(),
        reference_number="FCR-123456789ABC",
        customer_id=uuid4(),
        title="Complaint title",
        description="Complaint description",
        current_status=status,
        final_category_id=None,
        final_department_id=None,
        final_urgency=None,
    )


def _assert_transaction_neutral(repository: MagicMock) -> None:
    repository.commit.assert_not_awaited()
    repository.rollback.assert_not_awaited()
    repository.begin.assert_not_awaited()


def test_service_imports_exports_and_resource_isolation() -> None:
    expected_auth_exports = {
        "AuthenticationError",
        "AuthenticationResult",
        "AuthService",
        "DuplicateEmailError",
        "InactiveUserError",
        "InvalidCredentialsError",
        "UserNotFoundError",
        "create_access_token_for_user",
    }
    expected_complaint_exports = {
        "ComplaintAccessDeniedError",
        "ComplaintNotFoundError",
        "ComplaintService",
        "ComplaintServiceError",
        "InvalidComplaintDataError",
        "InvalidComplaintRoutingError",
        "InvalidComplaintStatusTransitionError",
    }
    expected_prediction_exports = {
        "ActiveModelVersionNotFoundError",
        "DuplicatePredictionError",
        "InvalidPredictionOutputError",
        "PredictionExecutionError",
        "PredictionNotAllowedError",
        "PredictionNotFoundError",
        "PredictionService",
        "PredictionServiceError",
    }
    engine_cache_before = get_engine.cache_info()
    session_cache_before = get_session_factory.cache_info()

    assert set(services.__all__) == (
        expected_auth_exports | expected_complaint_exports | expected_prediction_exports
    )
    assert issubclass(ComplaintServiceError, Exception)
    assert issubclass(AuthenticationError, Exception)
    assert get_engine.cache_info() == engine_cache_before
    assert get_session_factory.cache_info() == session_cache_before
    assert not any(isinstance(value, (ComplaintService, AuthService)) for value in vars(services).values())


def test_reference_number_format_randomness_and_privacy() -> None:
    first = _generate_reference_number()
    second = _generate_reference_number()

    assert re.fullmatch(r"FCR-[0-9A-F]{12}", first)
    assert first == first.upper()
    assert first != second
    assert "customer@example.com" not in first


@pytest.mark.anyio
async def test_successful_complaint_creation_and_initial_history() -> None:
    repository = _repository()
    customer = _user()
    generated_id = uuid4()

    async def flush_side_effect() -> None:
        complaint = repository.add.await_args.args[0]
        if complaint.__dict__.get("id") is None:
            complaint.id = generated_id

    repository.flush.side_effect = flush_side_effect
    repository.refresh.side_effect = lambda complaint: complaint

    result = await ComplaintService(repository).create_complaint(
        customer=customer,
        title="  Payment  dispute  ",
        description="  Merchant  charged twice  ",
    )

    repository.add.assert_awaited_once_with(result)
    assert repository.flush.await_count == 2
    repository.refresh.assert_awaited_once_with(result)
    assert result.reference_number.startswith("FCR-")
    assert result.customer_id == customer.id
    assert result.title == "Payment  dispute"
    assert result.description == "Merchant  charged twice"
    assert result.current_status == ComplaintStatus.SUBMITTED
    assert result.final_category_id is None
    assert result.final_department_id is None
    assert result.final_urgency is None
    repository.session.add.assert_called_once()
    history = repository.session.add.call_args.args[0]
    assert isinstance(history, ComplaintStatusHistory)
    assert history.complaint is result
    assert history.complaint_id == generated_id
    assert history.previous_status is None
    assert history.new_status == ComplaintStatus.SUBMITTED
    assert history.changed_by_user_id == customer.id
    assert history.change_source == ComplaintChangeSource.CUSTOMER
    assert history.reason is None
    assert result.status_history == [history]
    assert result.predictions == []
    assert result.reviews == []
    _assert_transaction_neutral(repository)


@pytest.mark.anyio
async def test_creation_returns_refreshed_complaint() -> None:
    repository = _repository()
    refreshed = _complaint()

    async def flush_side_effect() -> None:
        created = repository.add.await_args.args[0]
        created.id = created.__dict__.get("id") or uuid4()

    repository.flush.side_effect = flush_side_effect
    repository.refresh.return_value = refreshed

    result = await ComplaintService(repository).create_complaint(
        customer=_user(role_name=None),
        title="Valid title",
        description="Valid description",
    )

    assert result is refreshed


@pytest.mark.parametrize(
    ("customer", "title", "description", "exception_type"),
    [
        (_user(), "", "description", InvalidComplaintDataError),
        (_user(), "x" * 201, "description", InvalidComplaintDataError),
        (_user(), "title", "   ", InvalidComplaintDataError),
        (_user(), "title", "x" * 10_001, InvalidComplaintDataError),
        (_user(active=False), "title", "description", ComplaintAccessDeniedError),
        (_user(role_name="reviewer"), "title", "description", ComplaintAccessDeniedError),
        (_user(role_name="administrator"), "title", "description", ComplaintAccessDeniedError),
    ],
)
@pytest.mark.anyio
async def test_creation_validation_has_no_persistence(
    customer: User,
    title: str,
    description: str,
    exception_type: type[Exception],
) -> None:
    repository = _repository()

    with pytest.raises(exception_type):
        await ComplaintService(repository).create_complaint(
            customer=customer,
            title=title,
            description=description,
        )

    repository.add.assert_not_awaited()
    repository.flush.assert_not_awaited()
    repository.refresh.assert_not_awaited()
    repository.session.add.assert_not_called()


@pytest.mark.anyio
async def test_creation_rejects_missing_customer_id() -> None:
    customer = User(
        role_id=uuid4(), email="user@example.com", password_hash="unused",
        full_name="User", is_active=True, email_verified=False,
    )
    repository = _repository()

    with pytest.raises(InvalidComplaintDataError):
        await ComplaintService(repository).create_complaint(
            customer=customer, title="Title", description="Description"
        )
    repository.add.assert_not_awaited()


@pytest.mark.anyio
async def test_get_complaint_found_and_missing() -> None:
    repository = _repository()
    complaint = _complaint()
    repository.get_by_id.return_value = complaint
    service = ComplaintService(repository)

    assert await service.get_complaint(complaint.id) is complaint
    repository.get_by_id.return_value = None
    with pytest.raises(ComplaintNotFoundError):
        await service.get_complaint(uuid4())
    repository.refresh.assert_not_awaited()
    repository.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_customer_complaint_ownership() -> None:
    repository = _repository()
    complaint = _complaint()
    repository.get_by_id.return_value = complaint
    service = ComplaintService(repository)

    assert await service.get_customer_complaint(
        complaint_id=complaint.id, customer_id=complaint.customer_id
    ) is complaint
    with pytest.raises(ComplaintAccessDeniedError) as caught:
        await service.get_customer_complaint(
            complaint_id=complaint.id, customer_id=uuid4()
        )
    assert "owner" not in str(caught.value).lower()
    assert "customer" not in str(caught.value).lower()


@pytest.mark.anyio
async def test_customer_listing_delegates_and_returns_same_list() -> None:
    repository = _repository()
    complaints = [_complaint()]
    repository.list_for_customer.return_value = complaints
    customer_id = uuid4()

    result = await ComplaintService(repository).list_customer_complaints(
        customer_id=customer_id, offset=3, limit=20
    )

    assert result is complaints
    repository.list_for_customer.assert_awaited_once_with(
        customer_id, offset=3, limit=20
    )
    repository.flush.assert_not_awaited()


@pytest.mark.parametrize(
    "statuses",
    [None, [ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.UNDER_REVIEW]],
)
@pytest.mark.anyio
async def test_review_queue_delegates_statuses_unchanged(statuses) -> None:
    repository = _repository()
    complaints = [_complaint(ComplaintStatus.AWAITING_REVIEW)]
    repository.list_review_queue.return_value = complaints

    result = await ComplaintService(repository).list_review_queue(
        statuses=statuses, offset=2, limit=10
    )

    assert result is complaints
    repository.list_review_queue.assert_awaited_once_with(
        statuses=statuses, offset=2, limit=10
    )


@pytest.mark.anyio
async def test_listing_errors_propagate() -> None:
    repository = _repository()
    repository.list_for_customer.side_effect = ValueError("pagination")
    with pytest.raises(ValueError, match="pagination"):
        await ComplaintService(repository).list_customer_complaints(
            customer_id=uuid4(), offset=-1
        )


ALLOWED_TRANSITIONS = [
    (ComplaintStatus.SUBMITTED, ComplaintStatus.PREDICTION_PENDING),
    (ComplaintStatus.SUBMITTED, ComplaintStatus.AWAITING_REVIEW),
    (ComplaintStatus.SUBMITTED, ComplaintStatus.CLOSED),
    (ComplaintStatus.PREDICTION_PENDING, ComplaintStatus.PREDICTION_COMPLETED),
    (ComplaintStatus.PREDICTION_PENDING, ComplaintStatus.PREDICTION_FAILED),
    (ComplaintStatus.PREDICTION_PENDING, ComplaintStatus.AWAITING_REVIEW),
    (ComplaintStatus.PREDICTION_COMPLETED, ComplaintStatus.AWAITING_REVIEW),
    (ComplaintStatus.PREDICTION_COMPLETED, ComplaintStatus.ROUTED),
    (ComplaintStatus.PREDICTION_COMPLETED, ComplaintStatus.CLOSED),
    (ComplaintStatus.PREDICTION_FAILED, ComplaintStatus.AWAITING_REVIEW),
    (ComplaintStatus.PREDICTION_FAILED, ComplaintStatus.CLOSED),
    (ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.UNDER_REVIEW),
    (ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.ROUTED),
    (ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.CLOSED),
    (ComplaintStatus.UNDER_REVIEW, ComplaintStatus.AWAITING_REVIEW),
    (ComplaintStatus.UNDER_REVIEW, ComplaintStatus.ROUTED),
    (ComplaintStatus.UNDER_REVIEW, ComplaintStatus.CLOSED),
    (ComplaintStatus.ROUTED, ComplaintStatus.CLOSED),
]


@pytest.mark.parametrize(("previous", "new"), ALLOWED_TRANSITIONS)
@pytest.mark.anyio
async def test_every_allowed_status_transition(
    previous: ComplaintStatus, new: ComplaintStatus
) -> None:
    repository = _repository()
    complaint = _complaint(previous)
    repository.refresh.side_effect = lambda value: value
    changed_by = uuid4()

    result = await ComplaintService(repository).transition_status(
        complaint=complaint,
        new_status=new,
        changed_by_user_id=changed_by,
        source=ComplaintChangeSource.REVIEWER,
        notes="  reviewed  carefully  ",
    )

    assert result is complaint
    assert complaint.current_status == new
    repository.session.add.assert_called_once()
    history = repository.session.add.call_args.args[0]
    assert history.previous_status == previous
    assert history.new_status == new
    assert history.changed_by_user_id == changed_by
    assert history.change_source == ComplaintChangeSource.REVIEWER
    assert history.reason == "reviewed  carefully"
    repository.flush.assert_awaited_once_with()
    repository.refresh.assert_awaited_once_with(complaint)
    _assert_transaction_neutral(repository)


@pytest.mark.parametrize(
    ("previous", "new"),
    [
        (ComplaintStatus.SUBMITTED, ComplaintStatus.SUBMITTED),
        (ComplaintStatus.CLOSED, ComplaintStatus.SUBMITTED),
        (ComplaintStatus.ROUTED, ComplaintStatus.AWAITING_REVIEW),
        (ComplaintStatus.PREDICTION_COMPLETED, ComplaintStatus.PREDICTION_PENDING),
        (ComplaintStatus.SUBMITTED, ComplaintStatus.UNDER_REVIEW),
        (ComplaintStatus.SUBMITTED, "routed"),
    ],
)
@pytest.mark.anyio
async def test_forbidden_transition_does_not_mutate_or_persist(previous, new) -> None:
    repository = _repository()
    complaint = _complaint(previous)

    with pytest.raises(InvalidComplaintStatusTransitionError):
        await ComplaintService(repository).transition_status(
            complaint=complaint,
            new_status=new,
            changed_by_user_id=uuid4(),
            source=ComplaintChangeSource.SYSTEM,
        )

    assert complaint.current_status == previous
    repository.session.add.assert_not_called()
    repository.flush.assert_not_awaited()
    repository.refresh.assert_not_awaited()


@pytest.mark.anyio
async def test_invalid_transition_notes_or_source_do_not_mutate() -> None:
    for source, notes in [("system", None), (ComplaintChangeSource.SYSTEM, "x" * 2_001)]:
        repository = _repository()
        complaint = _complaint()
        with pytest.raises(InvalidComplaintDataError):
            await ComplaintService(repository).transition_status(
                complaint=complaint,
                new_status=ComplaintStatus.AWAITING_REVIEW,
                changed_by_user_id=None,
                source=source,
                notes=notes,
            )
        assert complaint.current_status == ComplaintStatus.SUBMITTED
        repository.session.add.assert_not_called()


@pytest.mark.anyio
async def test_valid_routing_sets_final_fields_and_creates_one_history() -> None:
    repository = _repository()
    complaint = _complaint(ComplaintStatus.AWAITING_REVIEW)
    repository.refresh.side_effect = lambda value: value
    category_id = uuid4()
    department_id = uuid4()
    changed_by = uuid4()

    result = await ComplaintService(repository).assign_routing(
        complaint=complaint,
        category_id=category_id,
        department_id=department_id,
        urgency=ComplaintUrgency.CRITICAL,
        changed_by_user_id=changed_by,
        source=ComplaintChangeSource.REVIEWER,
        notes="  final routing  ",
    )

    assert result is complaint
    assert complaint.final_category_id == category_id
    assert complaint.final_department_id == department_id
    assert complaint.final_urgency == ComplaintUrgency.CRITICAL
    assert complaint.current_status == ComplaintStatus.ROUTED
    repository.session.add.assert_called_once()
    history = repository.session.add.call_args.args[0]
    assert history.previous_status == ComplaintStatus.AWAITING_REVIEW
    assert history.new_status == ComplaintStatus.ROUTED
    assert history.reason == "final routing"
    assert complaint.predictions == []
    assert complaint.reviews == []
    _assert_transaction_neutral(repository)


@pytest.mark.parametrize(
    "overrides",
    [
        {"category_id": None},
        {"department_id": None},
        {"urgency": "high"},
        {"changed_by_user_id": None},
        {"source": "reviewer"},
    ],
)
@pytest.mark.anyio
async def test_invalid_routing_does_not_partially_mutate(overrides: dict) -> None:
    repository = _repository()
    complaint = _complaint(ComplaintStatus.AWAITING_REVIEW)
    values = {
        "complaint": complaint,
        "category_id": uuid4(),
        "department_id": uuid4(),
        "urgency": ComplaintUrgency.HIGH,
        "changed_by_user_id": uuid4(),
        "source": ComplaintChangeSource.ADMINISTRATOR,
    }
    values.update(overrides)

    with pytest.raises(InvalidComplaintRoutingError):
        await ComplaintService(repository).assign_routing(**values)

    assert complaint.final_category_id is None
    assert complaint.final_department_id is None
    assert complaint.final_urgency is None
    assert complaint.current_status == ComplaintStatus.AWAITING_REVIEW
    repository.session.add.assert_not_called()
    repository.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_closed_complaint_cannot_be_routed() -> None:
    repository = _repository()
    complaint = _complaint(ComplaintStatus.CLOSED)
    with pytest.raises(InvalidComplaintRoutingError):
        await ComplaintService(repository).assign_routing(
            complaint=complaint,
            category_id=uuid4(),
            department_id=uuid4(),
            urgency=ComplaintUrgency.HIGH,
            changed_by_user_id=uuid4(),
            source=ComplaintChangeSource.ADMINISTRATOR,
        )
    assert complaint.current_status == ComplaintStatus.CLOSED


@pytest.mark.anyio
async def test_exception_messages_and_logs_do_not_disclose_complaint_text(
    capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    repository = _repository()
    title = "private complaint title"
    description = "private complaint description"

    with pytest.raises(InvalidComplaintDataError) as caught:
        await ComplaintService(repository).create_complaint(
            customer=_user(), title=title, description=" "
        )

    captured = capsys.readouterr()
    combined = f"{caught.value} {captured.out} {captured.err} {caplog.text}"
    assert title not in combined
    assert description not in combined
    assert "database" not in str(caught.value).lower()
