"""Transaction-neutral human review lifecycle orchestration."""

from datetime import datetime, timezone
from uuid import UUID

from app.models import (
    Complaint,
    ComplaintChangeSource,
    ComplaintStatus,
    ComplaintUrgency,
    Prediction,
    Review,
    ReviewOutcome,
    User,
)
from app.repositories import ComplaintRepository, PredictionRepository, ReviewRepository
from app.services.complaint import ComplaintService


class ReviewServiceError(Exception):
    """Base exception for review-service failures."""


class ReviewNotAllowedError(ReviewServiceError):
    """Raised when the requested review action is not allowed."""


class ReviewNotFoundError(ReviewServiceError):
    """Raised when a review cannot be found."""


class ReviewAccessDeniedError(ReviewServiceError):
    """Raised when a user cannot perform human review."""


class DuplicateReviewError(ReviewServiceError):
    """Raised when a prediction already has a review."""


class InvalidReviewDataError(ReviewServiceError):
    """Raised when review input is invalid."""


class PredictionForReviewNotFoundError(ReviewServiceError):
    """Raised when a prediction cannot safely be resolved for review."""


_ACCESS_DENIED = "Review access is denied."
_NOT_ALLOWED = "Review is not allowed."
_NOT_FOUND = "Review was not found."
_DUPLICATE = "A review already exists."
_INVALID_DATA = "Review data is invalid."
_PREDICTION_NOT_FOUND = "Prediction for review was not found."
_COMMENT_MAX_LENGTH = 2_000
_REVIEW_ROLES = frozenset({"reviewer", "administrator"})


class ReviewService:
    """Coordinate human decisions without owning a database transaction."""

    def __init__(
        self,
        *,
        review_repository: ReviewRepository,
        prediction_repository: PredictionRepository,
        complaint_repository: ComplaintRepository,
        complaint_service: ComplaintService,
    ) -> None:
        self._review_repository = review_repository
        self._prediction_repository = prediction_repository
        self._complaint_repository = complaint_repository
        self._complaint_service = complaint_service

    @staticmethod
    def _validate_reviewer(reviewer: User) -> UUID:
        reviewer_id = reviewer.__dict__.get("id")
        role = reviewer.__dict__.get("role")
        try:
            role_name = role.name.strip().lower()
        except AttributeError:
            raise ReviewAccessDeniedError(_ACCESS_DENIED) from None
        if (
            not isinstance(reviewer_id, UUID)
            or reviewer.__dict__.get("is_active") is not True
            or role_name
            not in _REVIEW_ROLES
        ):
            raise ReviewAccessDeniedError(_ACCESS_DENIED)
        return reviewer_id

    @staticmethod
    def _normalize_review_comment(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise InvalidReviewDataError(_INVALID_DATA)
        normalized = value.strip()
        if not normalized:
            return None
        if len(normalized) > _COMMENT_MAX_LENGTH:
            raise InvalidReviewDataError(_INVALID_DATA)
        return normalized

    @staticmethod
    def _validate_claim_allowed(complaint: Complaint) -> None:
        if (
            not isinstance(complaint.__dict__.get("id"), UUID)
            or complaint.current_status is not ComplaintStatus.AWAITING_REVIEW
        ):
            raise ReviewNotAllowedError(_NOT_ALLOWED)

    @staticmethod
    def _validate_outcome_allowed(complaint: Complaint) -> None:
        if (
            not isinstance(complaint.__dict__.get("id"), UUID)
            or complaint.current_status is not ComplaintStatus.UNDER_REVIEW
        ):
            raise ReviewNotAllowedError(_NOT_ALLOWED)

    async def _get_prediction_for_review(
        self,
        *,
        prediction_id: UUID,
        complaint: Complaint,
    ) -> Prediction:
        if not isinstance(prediction_id, UUID):
            raise PredictionForReviewNotFoundError(_PREDICTION_NOT_FOUND)
        prediction = await self._prediction_repository.get_by_id(prediction_id)
        if prediction is None or prediction.complaint_id != complaint.__dict__.get("id"):
            raise PredictionForReviewNotFoundError(_PREDICTION_NOT_FOUND)
        if (
            prediction.output_valid is not True
            or not isinstance(prediction.predicted_category_id, UUID)
            or not isinstance(prediction.predicted_department_id, UUID)
            or not isinstance(prediction.predicted_urgency, ComplaintUrgency)
        ):
            raise ReviewNotAllowedError(_NOT_ALLOWED)
        return prediction

    async def _ensure_no_review(self, prediction_id: UUID) -> None:
        if await self._review_repository.get_for_prediction(prediction_id) is not None:
            raise DuplicateReviewError(_DUPLICATE)

    async def claim_review(
        self,
        *,
        complaint: Complaint,
        reviewer: User,
    ) -> Complaint:
        reviewer_id = self._validate_reviewer(reviewer)
        self._validate_claim_allowed(complaint)
        return await self._complaint_service.transition_status(
            complaint=complaint,
            new_status=ComplaintStatus.UNDER_REVIEW,
            changed_by_user_id=reviewer_id,
            source=ComplaintChangeSource.REVIEWER,
        )

    async def _validate_completed_review(
        self,
        *,
        complaint: Complaint,
        prediction: Prediction,
        reviewer: User,
        comment: str | None,
    ) -> tuple[UUID, Prediction, str | None]:
        reviewer_id = self._validate_reviewer(reviewer)
        self._validate_outcome_allowed(complaint)
        prediction_id = prediction.__dict__.get("id")
        persisted_prediction = await self._get_prediction_for_review(
            prediction_id=prediction_id,
            complaint=complaint,
        )
        await self._ensure_no_review(persisted_prediction.id)
        normalized_comment = self._normalize_review_comment(comment)
        return reviewer_id, persisted_prediction, normalized_comment

    async def _persist_review(self, review: Review) -> Review:
        await self._review_repository.add(review)
        await self._review_repository.flush()
        return await self._review_repository.refresh(review)

    async def approve_prediction(
        self,
        *,
        complaint: Complaint,
        prediction: Prediction,
        reviewer: User,
        comment: str | None = None,
    ) -> Review:
        reviewer_id, prediction, comment = await self._validate_completed_review(
            complaint=complaint,
            prediction=prediction,
            reviewer=reviewer,
            comment=comment,
        )
        review = Review(
            complaint_id=complaint.id,
            prediction_id=prediction.id,
            reviewer_id=reviewer_id,
            outcome=ReviewOutcome.APPROVED,
            approved_category_id=prediction.predicted_category_id,
            approved_department_id=prediction.predicted_department_id,
            approved_urgency=prediction.predicted_urgency,
            comments=comment,
            started_at=None,
            completed_at=datetime.now(timezone.utc),
        )
        review = await self._persist_review(review)
        await self._complaint_service.assign_routing(
            complaint=complaint,
            category_id=prediction.predicted_category_id,
            department_id=prediction.predicted_department_id,
            urgency=prediction.predicted_urgency,
            changed_by_user_id=reviewer_id,
            source=ComplaintChangeSource.REVIEWER,
            notes=comment,
        )
        return review

    async def correct_prediction(
        self,
        *,
        complaint: Complaint,
        prediction: Prediction,
        reviewer: User,
        category_id: UUID,
        department_id: UUID,
        urgency: ComplaintUrgency,
        comment: str | None = None,
    ) -> Review:
        reviewer_id, prediction, comment = await self._validate_completed_review(
            complaint=complaint,
            prediction=prediction,
            reviewer=reviewer,
            comment=comment,
        )
        if (
            not isinstance(category_id, UUID)
            or not isinstance(department_id, UUID)
            or not isinstance(urgency, ComplaintUrgency)
        ):
            raise InvalidReviewDataError(_INVALID_DATA)
        review = Review(
            complaint_id=complaint.id,
            prediction_id=prediction.id,
            reviewer_id=reviewer_id,
            outcome=ReviewOutcome.CORRECTED,
            approved_category_id=category_id,
            approved_department_id=department_id,
            approved_urgency=urgency,
            comments=comment,
            started_at=None,
            completed_at=datetime.now(timezone.utc),
        )
        review = await self._persist_review(review)
        await self._complaint_service.assign_routing(
            complaint=complaint,
            category_id=category_id,
            department_id=department_id,
            urgency=urgency,
            changed_by_user_id=reviewer_id,
            source=ComplaintChangeSource.REVIEWER,
            notes=comment,
        )
        return review

    async def reject_prediction(
        self,
        *,
        complaint: Complaint,
        prediction: Prediction,
        reviewer: User,
        comment: str | None = None,
    ) -> Review:
        reviewer_id, prediction, comment = await self._validate_completed_review(
            complaint=complaint,
            prediction=prediction,
            reviewer=reviewer,
            comment=comment,
        )
        review = Review(
            complaint_id=complaint.id,
            prediction_id=prediction.id,
            reviewer_id=reviewer_id,
            outcome=ReviewOutcome.REJECTED,
            approved_category_id=None,
            approved_department_id=None,
            approved_urgency=None,
            comments=comment,
            started_at=None,
            completed_at=datetime.now(timezone.utc),
        )
        review = await self._persist_review(review)
        await self._complaint_service.transition_status(
            complaint=complaint,
            new_status=ComplaintStatus.AWAITING_REVIEW,
            changed_by_user_id=reviewer_id,
            source=ComplaintChangeSource.REVIEWER,
            notes=comment,
        )
        return review

    async def get_review(self, review_id: UUID) -> Review:
        review = await self._review_repository.get_by_id(review_id)
        if review is None:
            raise ReviewNotFoundError(_NOT_FOUND)
        return review

    async def list_prediction_reviews(
        self,
        *,
        prediction_id: UUID,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Review]:
        self._review_repository._validate_pagination(offset, limit)
        review = await self._review_repository.get_for_prediction(prediction_id)
        if review is None or offset > 0:
            return []
        return [review]

    async def list_review_queue(
        self,
        *,
        offset: int = 0,
        limit: int = 100,
    ) -> list[Complaint]:
        return await self._complaint_service.list_review_queue(
            statuses=(ComplaintStatus.AWAITING_REVIEW, ComplaintStatus.UNDER_REVIEW),
            offset=offset,
            limit=limit,
        )
