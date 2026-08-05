"""Tests for role-protected human review REST endpoints."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
from pydantic import ValidationError
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import (
    get_complaint_repository,
    get_prediction_repository,
    get_review_repository,
    get_review_service,
    get_transactional_complaint_repository,
    get_transactional_prediction_repository,
    get_transactional_review_repository,
    get_transactional_review_service,
)
from app.authz import require_reviewer_or_administrator
from app.core.config import Settings
from app.main import create_app
from app.models import (
    Complaint,
    ComplaintStatus,
    ComplaintUrgency,
    Prediction,
    Review,
    ReviewOutcome,
    Role,
    User,
)
from app.repositories import ComplaintRepository, PredictionRepository, ReviewRepository
from app.schemas import ReviewActionRequest, ReviewCorrectionRequest, ReviewResponse
from app.services import (
    ComplaintService,
    DuplicateReviewError,
    ReviewNotAllowedError,
    ReviewNotFoundError,
    ReviewService,
)


def _user(role="reviewer") -> User:
    role_id = uuid4()
    user = User(
        id=uuid4(), role_id=role_id, email="reviewer@example.com",
        password_hash="secret", full_name="Reviewer", is_active=True,
        email_verified=True,
    )
    user.role = Role(id=role_id, name=role, display_name="Role", is_active=True)
    return user


def _complaint(status=ComplaintStatus.AWAITING_REVIEW) -> Complaint:
    now = datetime.now(timezone.utc)
    return Complaint(
        id=uuid4(), reference_number="FCR-QUEUE", customer_id=uuid4(),
        title="Safe title", description="Never expose this description",
        current_status=status, final_category_id=None, final_department_id=None,
        final_urgency=None, created_at=now, updated_at=now,
    )


def _prediction(complaint: Complaint) -> Prediction:
    return Prediction(
        id=uuid4(), complaint_id=complaint.id, model_version_id=uuid4(),
        predicted_category_id=uuid4(), predicted_department_id=uuid4(),
        predicted_urgency=ComplaintUrgency.HIGH, confidence_score=0.9,
        raw_output={"private": True}, output_valid=True,
    )


def _review(complaint: Complaint, prediction: Prediction, reviewer: User) -> Review:
    now = datetime.now(timezone.utc)
    return Review(
        id=uuid4(), complaint_id=complaint.id, prediction_id=prediction.id,
        reviewer_id=reviewer.id, outcome=ReviewOutcome.APPROVED,
        approved_category_id=prediction.predicted_category_id,
        approved_department_id=prediction.predicted_department_id,
        approved_urgency=prediction.predicted_urgency, comments="safe",
        started_at=None, completed_at=now, created_at=now,
    )


def _app(service, complaint_repo=None, prediction_repo=None, user=None):
    application = create_app(Settings())
    application.dependency_overrides[require_reviewer_or_administrator] = lambda: user or _user()
    for dependency in (get_review_service, get_transactional_review_service):
        application.dependency_overrides[dependency] = lambda: service
    if complaint_repo is not None:
        for dependency in (get_complaint_repository, get_transactional_complaint_repository):
            application.dependency_overrides[dependency] = lambda: complaint_repo
    if prediction_repo is not None:
        for dependency in (get_prediction_repository, get_transactional_prediction_repository):
            application.dependency_overrides[dependency] = lambda: prediction_repo
    return application


@pytest.mark.parametrize(
    "payload",
    [
        {"prediction_id": "bad"},
        {"prediction_id": str(uuid4()), "comment": "x" * 2001},
        {"prediction_id": str(uuid4()), "extra": True},
    ],
)
def test_action_schema_rejects_invalid_data(payload) -> None:
    with pytest.raises(ValidationError):
        ReviewActionRequest.model_validate(payload)


def test_correction_schema_and_safe_review_response() -> None:
    request = ReviewCorrectionRequest(
        prediction_id=uuid4(), category_id=uuid4(), department_id=uuid4(),
        urgency=ComplaintUrgency.CRITICAL,
    )
    assert request.urgency is ComplaintUrgency.CRITICAL
    reviewer, complaint = _user(), _complaint()
    prediction = _prediction(complaint)
    data = ReviewResponse.model_validate(_review(complaint, prediction, reviewer)).model_dump()
    assert set(data) == {
        "id", "complaint_id", "prediction_id", "reviewer_id", "outcome",
        "approved_category_id", "approved_department_id", "approved_urgency",
        "comments", "started_at", "completed_at", "created_at",
    }


@pytest.mark.anyio
async def test_repository_and_service_dependencies_preserve_exact_objects() -> None:
    session = MagicMock(spec=AsyncSession)
    review_repo = await get_review_repository(session)
    transaction_review_repo = await get_transactional_review_repository(session)
    prediction_repo = await get_prediction_repository(session)
    transaction_prediction_repo = await get_transactional_prediction_repository(session)
    complaint_repo = MagicMock(spec=ComplaintRepository)
    complaint_service = MagicMock(spec=ComplaintService)
    service = get_review_service(review_repo, prediction_repo, complaint_repo, complaint_service)
    transaction_service = get_transactional_review_service(
        transaction_review_repo, transaction_prediction_repo,
        complaint_repo, complaint_service,
    )
    assert review_repo.session is session and prediction_repo.session is session
    assert service._review_repository is review_repo
    assert transaction_service._prediction_repository is transaction_prediction_repo
    for method in ("begin", "commit", "rollback", "flush", "execute"):
        getattr(session, method).assert_not_called()


@pytest.mark.anyio
async def test_queue_is_safe_and_passes_pagination() -> None:
    service = MagicMock(spec=ReviewService)
    service.list_review_queue = AsyncMock(return_value=[_complaint()])
    transport = httpx.ASGITransport(app=_app(service))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/reviews/queue?offset=2&limit=7")
    assert response.status_code == 200
    assert response.json()["count"] == 1
    assert "description" not in response.text and "customer_id" not in response.text
    service.list_review_queue.assert_awaited_once_with(offset=2, limit=7)


@pytest.mark.anyio
async def test_claim_resolves_complaint_and_passes_exact_objects() -> None:
    reviewer = _user()
    complaint = _complaint()
    claimed = _complaint(ComplaintStatus.UNDER_REVIEW)
    claimed.id = complaint.id
    repository = MagicMock(spec=ComplaintRepository)
    repository.get_by_id = AsyncMock(return_value=complaint)
    service = MagicMock(spec=ReviewService)
    service.claim_review = AsyncMock(return_value=claimed)
    transport = httpx.ASGITransport(app=_app(service, repository, user=reviewer))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/reviews/complaints/{complaint.id}/claim")
    assert response.status_code == 200
    assert response.json()["current_status"] == "under_review"
    service.claim_review.assert_awaited_once_with(complaint=complaint, reviewer=reviewer)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (DuplicateReviewError("hidden"), "Prediction has already been reviewed"),
        (ReviewNotAllowedError("hidden"), "Review action is not allowed"),
    ],
)
async def test_approve_maps_service_errors_generically(error, detail) -> None:
    reviewer, complaint = _user(), _complaint(ComplaintStatus.UNDER_REVIEW)
    prediction = _prediction(complaint)
    complaint_repo = MagicMock(spec=ComplaintRepository)
    complaint_repo.get_by_id = AsyncMock(return_value=complaint)
    prediction_repo = MagicMock(spec=PredictionRepository)
    prediction_repo.get_by_id = AsyncMock(return_value=prediction)
    service = MagicMock(spec=ReviewService)
    service.approve_prediction = AsyncMock(side_effect=error)
    transport = httpx.ASGITransport(
        app=_app(service, complaint_repo, prediction_repo, reviewer)
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            f"/api/reviews/complaints/{complaint.id}/approve",
            json={"prediction_id": str(prediction.id)},
        )
    assert response.status_code == 409
    assert response.json() == {"detail": detail}
    assert "hidden" not in response.text


@pytest.mark.anyio
@pytest.mark.parametrize("action", ["approve", "correct", "reject"])
async def test_outcome_actions_return_safe_persisted_review(action) -> None:
    reviewer, complaint = _user(), _complaint(ComplaintStatus.UNDER_REVIEW)
    prediction = _prediction(complaint)
    review = _review(complaint, prediction, reviewer)
    complaint_repo = MagicMock(spec=ComplaintRepository)
    complaint_repo.get_by_id = AsyncMock(return_value=complaint)
    prediction_repo = MagicMock(spec=PredictionRepository)
    prediction_repo.get_by_id = AsyncMock(return_value=prediction)
    service = MagicMock(spec=ReviewService)
    setattr(service, f"{action}_prediction", AsyncMock(return_value=review))
    payload = {"prediction_id": str(prediction.id), "comment": " exact "}
    if action == "correct":
        payload.update(category_id=str(uuid4()), department_id=str(uuid4()), urgency="high")
    transport = httpx.ASGITransport(app=_app(service, complaint_repo, prediction_repo, reviewer))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(f"/api/reviews/complaints/{complaint.id}/{action}", json=payload)
    assert response.status_code == 200
    assert "raw_output" not in response.text and "email" not in response.text


@pytest.mark.anyio
async def test_review_detail_and_missing_mapping() -> None:
    reviewer, complaint = _user(), _complaint()
    prediction = _prediction(complaint)
    review = _review(complaint, prediction, reviewer)
    service = MagicMock(spec=ReviewService)
    service.get_review = AsyncMock(return_value=review)
    transport = httpx.ASGITransport(app=_app(service, user=reviewer))
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/reviews/{review.id}")
        assert response.status_code == 200
        service.get_review.side_effect = ReviewNotFoundError("hidden")
        missing = await client.get(f"/api/reviews/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Review not found"}


def test_openapi_review_contract() -> None:
    schema = create_app(Settings()).openapi()
    paths = schema["paths"]
    expected = {
        "/api/reviews/queue", "/api/reviews/{review_id}",
        "/api/reviews/complaints/{complaint_id}/claim",
        "/api/reviews/complaints/{complaint_id}/approve",
        "/api/reviews/complaints/{complaint_id}/correct",
        "/api/reviews/complaints/{complaint_id}/reject",
    }
    assert expected <= set(paths)
    for path in expected:
        operation = next(iter(paths[path].values()))
        assert operation["tags"] == ["Human Review"]
        assert operation["security"]
