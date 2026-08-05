"""Tests for transaction-neutral human review orchestration."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.models import (
    Complaint,
    ComplaintChangeSource,
    ComplaintStatus,
    ComplaintUrgency,
    Prediction,
    Review,
    ReviewOutcome,
    Role,
    User,
)
from app.repositories import ComplaintRepository, PredictionRepository, ReviewRepository
from app.services import (
    ComplaintService,
    DuplicateReviewError,
    InvalidReviewDataError,
    PredictionForReviewNotFoundError,
    ReviewAccessDeniedError,
    ReviewNotAllowedError,
    ReviewNotFoundError,
    ReviewService,
)


def _reviewer(role_name="reviewer", *, active=True, with_id=True) -> User:
    role_id = uuid4()
    user = User(
        id=uuid4() if with_id else None,
        role_id=role_id,
        email="private@example.com",
        password_hash="hash",
        full_name="Reviewer",
        is_active=active,
        email_verified=True,
    )
    if role_name is not None:
        user.role = Role(
            id=role_id, name=role_name, display_name="Role", is_active=True
        )
    return user


def _complaint(status=ComplaintStatus.UNDER_REVIEW, *, with_id=True) -> Complaint:
    return Complaint(
        id=uuid4() if with_id else None,
        reference_number="FCR-REVIEW",
        customer_id=uuid4(),
        title="Private title",
        description="Private description",
        current_status=status,
        final_category_id=None,
        final_department_id=None,
        final_urgency=None,
    )


def _prediction(complaint: Complaint, *, valid=True) -> Prediction:
    return Prediction(
        id=uuid4(),
        complaint_id=complaint.id,
        model_version_id=uuid4(),
        predicted_category_id=uuid4() if valid else None,
        predicted_department_id=uuid4() if valid else None,
        predicted_urgency=ComplaintUrgency.HIGH if valid else None,
        confidence_score=0.9,
        raw_output={"private": "evidence"},
        output_valid=valid,
    )


def _service():
    review_repo = MagicMock(spec=ReviewRepository)
    prediction_repo = MagicMock(spec=PredictionRepository)
    complaint_repo = MagicMock(spec=ComplaintRepository)
    complaint_service = MagicMock(spec=ComplaintService)
    service = ReviewService(
        review_repository=review_repo,
        prediction_repository=prediction_repo,
        complaint_repository=complaint_repo,
        complaint_service=complaint_service,
    )
    return service, review_repo, prediction_repo, complaint_repo, complaint_service


def test_constructor_preserves_dependencies_without_side_effects() -> None:
    service, review_repo, prediction_repo, complaint_repo, complaint_service = _service()
    assert service._review_repository is review_repo
    assert service._prediction_repository is prediction_repo
    assert service._complaint_repository is complaint_repo
    assert service._complaint_service is complaint_service
    assert not any(item.mock_calls for item in (review_repo, prediction_repo, complaint_repo, complaint_service))


@pytest.mark.parametrize("role", ["reviewer", "administrator"])
def test_active_review_roles_are_accepted(role) -> None:
    reviewer = _reviewer(role)
    assert ReviewService._validate_reviewer(reviewer) == reviewer.id


@pytest.mark.parametrize(
    "reviewer",
    [
        _reviewer("customer"),
        _reviewer("unsupported"),
        _reviewer("reviewer", active=False),
        _reviewer("reviewer", with_id=False),
        _reviewer(None),
    ],
)
def test_invalid_reviewers_are_rejected_without_lazy_loading(reviewer) -> None:
    with pytest.raises(ReviewAccessDeniedError):
        ReviewService._validate_reviewer(reviewer)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("   ", None), ("  useful  comment  ", "useful  comment")],
)
def test_comment_normalization(value, expected) -> None:
    assert ReviewService._normalize_review_comment(value) == expected


@pytest.mark.parametrize("value", [object(), "x" * 2001])
def test_invalid_comment_is_generic(value) -> None:
    with pytest.raises(InvalidReviewDataError) as caught:
        ReviewService._normalize_review_comment(value)
    assert "xxxx" not in str(caught.value)


@pytest.mark.anyio
async def test_claim_transitions_only_and_returns_service_result() -> None:
    service, review_repo, _, _, complaint_service = _service()
    complaint = _complaint(ComplaintStatus.AWAITING_REVIEW)
    reviewer = _reviewer()
    transitioned = _complaint(ComplaintStatus.UNDER_REVIEW)
    complaint_service.transition_status = AsyncMock(return_value=transitioned)
    assert await service.claim_review(complaint=complaint, reviewer=reviewer) is transitioned
    complaint_service.transition_status.assert_awaited_once_with(
        complaint=complaint,
        new_status=ComplaintStatus.UNDER_REVIEW,
        changed_by_user_id=reviewer.id,
        source=ComplaintChangeSource.REVIEWER,
    )
    assert not review_repo.mock_calls


@pytest.mark.parametrize(
    "status",
    [status for status in ComplaintStatus if status is not ComplaintStatus.AWAITING_REVIEW],
)
def test_claim_rejects_other_statuses(status) -> None:
    with pytest.raises(ReviewNotAllowedError):
        ReviewService._validate_claim_allowed(_complaint(status))


@pytest.mark.anyio
async def test_prediction_validation_uses_repository_and_hides_mismatch() -> None:
    service, _, prediction_repo, _, _ = _service()
    complaint = _complaint()
    prediction = _prediction(complaint)
    prediction_repo.get_by_id = AsyncMock(return_value=prediction)
    assert await service._get_prediction_for_review(prediction_id=prediction.id, complaint=complaint) is prediction
    prediction_repo.get_by_id.return_value = None
    with pytest.raises(PredictionForReviewNotFoundError):
        await service._get_prediction_for_review(prediction_id=prediction.id, complaint=complaint)
    prediction_repo.get_by_id.return_value = _prediction(_complaint())
    with pytest.raises(PredictionForReviewNotFoundError):
        await service._get_prediction_for_review(prediction_id=prediction.id, complaint=complaint)
    prediction_repo.get_by_id.return_value = _prediction(complaint, valid=False)
    with pytest.raises(ReviewNotAllowedError):
        await service._get_prediction_for_review(prediction_id=prediction.id, complaint=complaint)


@pytest.mark.anyio
async def test_existing_review_blocks_before_persistence_or_routing() -> None:
    service, review_repo, prediction_repo, _, complaint_service = _service()
    complaint = _complaint()
    prediction = _prediction(complaint)
    prediction_repo.get_by_id = AsyncMock(return_value=prediction)
    review_repo.get_for_prediction = AsyncMock(return_value=Review(outcome=ReviewOutcome.APPROVED))
    with pytest.raises(DuplicateReviewError):
        await service.approve_prediction(complaint=complaint, prediction=prediction, reviewer=_reviewer())
    review_repo.add.assert_not_called()
    assert not complaint_service.mock_calls


def _ready_outcome(action="approve"):
    service, review_repo, prediction_repo, complaint_repo, complaint_service = _service()
    complaint = _complaint()
    prediction = _prediction(complaint)
    reviewer = _reviewer()
    prediction_repo.get_by_id = AsyncMock(return_value=prediction)
    review_repo.get_for_prediction = AsyncMock(return_value=None)
    review_repo.add = AsyncMock(side_effect=lambda review: review)
    review_repo.flush = AsyncMock()
    review_repo.refresh = AsyncMock(side_effect=lambda review: review)
    complaint_service.assign_routing = AsyncMock()
    complaint_service.transition_status = AsyncMock()
    return service, review_repo, complaint_service, complaint, prediction, reviewer


@pytest.mark.anyio
async def test_approval_persists_prediction_values_then_routes() -> None:
    service, repo, complaint_service, complaint, prediction, reviewer = _ready_outcome()
    original = dict(prediction.__dict__)
    review = await service.approve_prediction(
        complaint=complaint, prediction=prediction, reviewer=reviewer, comment="  good  "
    )
    assert review.outcome is ReviewOutcome.APPROVED
    assert review.approved_category_id == prediction.predicted_category_id
    assert review.comments == "good"
    repo.add.assert_awaited_once_with(review)
    repo.flush.assert_awaited_once_with()
    repo.refresh.assert_awaited_once_with(review)
    complaint_service.assign_routing.assert_awaited_once_with(
        complaint=complaint,
        category_id=prediction.predicted_category_id,
        department_id=prediction.predicted_department_id,
        urgency=prediction.predicted_urgency,
        changed_by_user_id=reviewer.id,
        source=ComplaintChangeSource.REVIEWER,
        notes="good",
    )
    assert prediction.__dict__ == original


@pytest.mark.anyio
async def test_correction_persists_reviewer_values_and_preserves_prediction() -> None:
    service, _, complaint_service, complaint, prediction, reviewer = _ready_outcome()
    category_id, department_id = uuid4(), uuid4()
    original = dict(prediction.__dict__)
    review = await service.correct_prediction(
        complaint=complaint,
        prediction=prediction,
        reviewer=reviewer,
        category_id=category_id,
        department_id=department_id,
        urgency=ComplaintUrgency.CRITICAL,
    )
    assert review.outcome is ReviewOutcome.CORRECTED
    assert review.approved_category_id == category_id
    complaint_service.assign_routing.assert_awaited_once_with(
        complaint=complaint,
        category_id=category_id,
        department_id=department_id,
        urgency=ComplaintUrgency.CRITICAL,
        changed_by_user_id=reviewer.id,
        source=ComplaintChangeSource.REVIEWER,
        notes=None,
    )
    assert prediction.__dict__ == original


@pytest.mark.anyio
@pytest.mark.parametrize("invalid", [("bad", uuid4(), ComplaintUrgency.HIGH), (uuid4(), "bad", ComplaintUrgency.HIGH), (uuid4(), uuid4(), "high")])
async def test_invalid_correction_has_no_persistence_or_routing(invalid) -> None:
    service, repo, complaint_service, complaint, prediction, reviewer = _ready_outcome()
    with pytest.raises(InvalidReviewDataError):
        await service.correct_prediction(
            complaint=complaint, prediction=prediction, reviewer=reviewer,
            category_id=invalid[0], department_id=invalid[1], urgency=invalid[2],
        )
    repo.add.assert_not_called()
    complaint_service.assign_routing.assert_not_called()


@pytest.mark.anyio
async def test_rejection_persists_without_routing_and_returns_to_queue() -> None:
    service, _, complaint_service, complaint, prediction, reviewer = _ready_outcome()
    review = await service.reject_prediction(
        complaint=complaint, prediction=prediction, reviewer=reviewer, comment=" no "
    )
    assert review.outcome is ReviewOutcome.REJECTED
    assert review.approved_category_id is None
    complaint_service.assign_routing.assert_not_called()
    complaint_service.transition_status.assert_awaited_once_with(
        complaint=complaint,
        new_status=ComplaintStatus.AWAITING_REVIEW,
        changed_by_user_id=reviewer.id,
        source=ComplaintChangeSource.REVIEWER,
        notes="no",
    )


@pytest.mark.anyio
async def test_read_methods_delegate_and_preserve_results() -> None:
    service, repo, _, _, complaint_service = _service()
    review = Review(id=uuid4())
    repo.get_by_id = AsyncMock(return_value=review)
    assert await service.get_review(review.id) is review
    repo.get_by_id.return_value = None
    with pytest.raises(ReviewNotFoundError):
        await service.get_review(uuid4())
    repo.get_for_prediction = AsyncMock(return_value=review)
    prediction_id = uuid4()
    assert await service.list_prediction_reviews(prediction_id=prediction_id) == [review]
    queue = [_complaint(ComplaintStatus.AWAITING_REVIEW)]
    complaint_service.list_review_queue = AsyncMock(return_value=queue)
    assert await service.list_review_queue(offset=2, limit=7) is queue
    complaint_service.list_review_queue.assert_awaited_once_with(
        statuses=(ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.UNDER_REVIEW),
        offset=2,
        limit=7,
    )
