"""Model-promotion workflow without deployment side effects."""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.db.mixins import utc_now
from app.models import ModelPromotionDecision, ModelPromotionStatus
from app.repositories import BenchmarkComparisonRepository, ModelPromotionRepository


class ModelPromotionServiceError(Exception):
    pass


class ModelPromotionNotFoundError(ModelPromotionServiceError):
    pass


class BenchmarkComparisonNotFoundForPromotionError(ModelPromotionServiceError):
    pass


class BenchmarkResultNotFoundForPromotionError(ModelPromotionServiceError):
    pass


class InvalidModelPromotionError(ModelPromotionServiceError):
    pass


class BenchmarkResultNotInComparisonError(ModelPromotionServiceError):
    pass


class BenchmarkResultModelMismatchError(ModelPromotionServiceError):
    pass


class NonWinningResultRequiresOverrideError(ModelPromotionServiceError):
    pass


class DuplicatePendingModelPromotionError(ModelPromotionServiceError):
    pass


class ModelPromotionStateConflictError(ModelPromotionServiceError):
    pass


class ModelPromotionPersistenceError(ModelPromotionServiceError):
    pass


@dataclass(frozen=True, slots=True)
class ModelPromotionCreateInput:
    benchmark_comparison_id: UUID
    selected_benchmark_result_id: UUID
    requested_by_user_id: UUID
    rationale: str
    override_winner: bool = False


@dataclass(frozen=True, slots=True)
class ModelPromotionReviewInput:
    promotion_id: UUID
    reviewed_by_user_id: UUID
    review_note: str


@dataclass(frozen=True, slots=True)
class ModelPromotionCancelInput:
    promotion_id: UUID
    cancelled_by_user_id: UUID
    cancellation_note: str


_INVALID = "Model promotion data is invalid."
_MAX_TEXT = 10_000


class ModelPromotionService:
    def __init__(
        self,
        promotion_repository: ModelPromotionRepository,
        comparison_repository: BenchmarkComparisonRepository,
    ) -> None:
        self._promotions = promotion_repository
        self._comparisons = comparison_repository

    async def create_promotion(
        self, value: ModelPromotionCreateInput
    ) -> ModelPromotionDecision:
        if not isinstance(value, ModelPromotionCreateInput):
            raise InvalidModelPromotionError(_INVALID)
        self._uuids(
            value.benchmark_comparison_id,
            value.selected_benchmark_result_id,
            value.requested_by_user_id,
        )
        rationale = self._text(value.rationale)
        if not isinstance(value.override_winner, bool):
            raise InvalidModelPromotionError(_INVALID)
        comparison = await self._comparisons.get_with_members(
            value.benchmark_comparison_id
        )
        if comparison is None:
            raise BenchmarkComparisonNotFoundForPromotionError(
                "Benchmark comparison was not found."
            )
        selected = self._member_result(
            comparison, value.selected_benchmark_result_id
        )
        self._validate_result_model(selected)
        override = value.override_winner
        if selected.id == comparison.winner_result_id:
            override = False
        elif not override:
            raise NonWinningResultRequiresOverrideError(
                "A non-winning result requires an override."
            )
        if await self._promotions.get_pending_for_comparison(comparison.id) is not None:
            raise DuplicatePendingModelPromotionError(
                "A pending model promotion already exists."
            )
        promotion = ModelPromotionDecision(
            benchmark_comparison_id=comparison.id,
            selected_benchmark_result_id=selected.id,
            selected_model_version_id=selected.model_version_id,
            status=ModelPromotionStatus.PENDING,
            rationale=rationale,
            override_winner=override,
            requested_by_user_id=value.requested_by_user_id,
            reviewed_by_user_id=None,
            requested_at=utc_now(),
            reviewed_at=None,
            review_note=None,
        )
        return await self._persist_new(promotion)

    async def approve_promotion(
        self, value: ModelPromotionReviewInput
    ) -> ModelPromotionDecision:
        promotion, user_id, note = await self._review_values(value)
        self._validate_persisted_consistency(promotion)
        return await self._transition(
            promotion, ModelPromotionStatus.APPROVED, user_id, note
        )

    async def reject_promotion(
        self, value: ModelPromotionReviewInput
    ) -> ModelPromotionDecision:
        promotion, user_id, note = await self._review_values(value)
        self._validate_persisted_consistency(promotion)
        return await self._transition(
            promotion, ModelPromotionStatus.REJECTED, user_id, note
        )

    async def cancel_promotion(
        self, value: ModelPromotionCancelInput
    ) -> ModelPromotionDecision:
        if not isinstance(value, ModelPromotionCancelInput):
            raise InvalidModelPromotionError(_INVALID)
        self._uuids(value.promotion_id, value.cancelled_by_user_id)
        note = self._text(value.cancellation_note)
        promotion = await self._get_pending(value.promotion_id)
        if value.cancelled_by_user_id != promotion.requested_by_user_id:
            raise InvalidModelPromotionError(_INVALID)
        self._validate_persisted_consistency(promotion)
        return await self._transition(
            promotion, ModelPromotionStatus.CANCELLED,
            value.cancelled_by_user_id, note,
        )

    async def get_promotion(self, promotion_id: UUID) -> ModelPromotionDecision:
        self._uuids(promotion_id)
        promotion = await self._promotions.get_with_details(promotion_id)
        if promotion is None:
            raise ModelPromotionNotFoundError("Model promotion was not found.")
        return promotion

    async def list_promotions(
        self,
        *,
        status: ModelPromotionStatus | None = None,
        offset: int = 0,
        limit: int = 100,
    ) -> list[ModelPromotionDecision]:
        return await self._promotions.list_promotions(
            status=status, offset=offset, limit=limit
        )

    async def _review_values(self, value: ModelPromotionReviewInput):
        if not isinstance(value, ModelPromotionReviewInput):
            raise InvalidModelPromotionError(_INVALID)
        self._uuids(value.promotion_id, value.reviewed_by_user_id)
        note = self._text(value.review_note)
        return await self._get_pending(value.promotion_id), value.reviewed_by_user_id, note

    async def _get_pending(self, promotion_id: UUID) -> ModelPromotionDecision:
        promotion = await self._promotions.get_with_details(promotion_id)
        if promotion is None:
            raise ModelPromotionNotFoundError("Model promotion was not found.")
        if promotion.status is not ModelPromotionStatus.PENDING:
            raise ModelPromotionStateConflictError(
                "Model promotion is not pending."
            )
        return promotion

    async def _persist_new(
        self, promotion: ModelPromotionDecision
    ) -> ModelPromotionDecision:
        try:
            await self._promotions.add_promotion(promotion)
            await self._promotions.flush()
            complete = await self._promotions.get_with_details(promotion.id)
        except IntegrityError as error:
            constraint_name = getattr(
                getattr(error.orig, "diag", None), "constraint_name", None
            )
            if constraint_name == "uq_model_promotion_decisions_pending_comparison":
                raise DuplicatePendingModelPromotionError(
                    "A pending model promotion already exists."
                ) from None
            raise ModelPromotionPersistenceError(
                "Model promotion could not be persisted."
            ) from None
        except Exception:
            raise ModelPromotionPersistenceError(
                "Model promotion could not be persisted."
            ) from None
        if complete is None:
            raise ModelPromotionPersistenceError(
                "Model promotion could not be persisted."
            )
        return complete

    async def _transition(
        self,
        promotion: ModelPromotionDecision,
        status: ModelPromotionStatus,
        user_id: UUID,
        note: str,
    ) -> ModelPromotionDecision:
        promotion.status = status
        promotion.reviewed_by_user_id = user_id
        promotion.reviewed_at = utc_now()
        promotion.review_note = note
        try:
            await self._promotions.flush()
            complete = await self._promotions.get_with_details(promotion.id)
        except Exception:
            raise ModelPromotionPersistenceError(
                "Model promotion could not be persisted."
            ) from None
        if complete is None:
            raise ModelPromotionPersistenceError(
                "Model promotion could not be persisted."
            )
        return complete

    @staticmethod
    def _member_result(comparison, result_id: UUID):
        member = next(
            (item for item in comparison.members if item.benchmark_result_id == result_id),
            None,
        )
        if member is None:
            raise BenchmarkResultNotInComparisonError(
                "Benchmark result is not part of the comparison."
            )
        if member.benchmark_result is None:
            raise BenchmarkResultNotFoundForPromotionError(
                "Benchmark result was not found."
            )
        return member.benchmark_result

    @staticmethod
    def _validate_result_model(result) -> None:
        if (
            result.model_version is None
            or not isinstance(result.model_version_id, UUID)
            or result.model_version.id != result.model_version_id
        ):
            raise BenchmarkResultModelMismatchError(
                "Benchmark result model version is inconsistent."
            )

    @classmethod
    def _validate_persisted_consistency(cls, promotion) -> None:
        comparison = promotion.benchmark_comparison
        if comparison is None:
            raise BenchmarkComparisonNotFoundForPromotionError(
                "Benchmark comparison was not found."
            )
        result = cls._member_result(comparison, promotion.selected_benchmark_result_id)
        if result.id != promotion.selected_benchmark_result_id:
            raise BenchmarkResultNotInComparisonError(
                "Benchmark result is not part of the comparison."
            )
        cls._validate_result_model(result)
        if (
            promotion.selected_model_version_id != result.model_version_id
            or promotion.selected_model_version is None
            or promotion.selected_model_version.id
            != promotion.selected_model_version_id
        ):
            raise BenchmarkResultModelMismatchError(
                "Benchmark result model version is inconsistent."
            )
        if result.id != comparison.winner_result_id and not promotion.override_winner:
            raise NonWinningResultRequiresOverrideError(
                "A non-winning result requires an override."
            )

    @staticmethod
    def _uuids(*values: object) -> None:
        if any(not isinstance(value, UUID) for value in values):
            raise InvalidModelPromotionError(_INVALID)

    @staticmethod
    def _text(value: object) -> str:
        if not isinstance(value, str):
            raise InvalidModelPromotionError(_INVALID)
        normalized = value.strip()
        if not normalized or len(normalized) > _MAX_TEXT:
            raise InvalidModelPromotionError(_INVALID)
        return normalized


__all__ = [
    "BenchmarkComparisonNotFoundForPromotionError",
    "BenchmarkResultModelMismatchError",
    "BenchmarkResultNotFoundForPromotionError",
    "BenchmarkResultNotInComparisonError",
    "DuplicatePendingModelPromotionError",
    "InvalidModelPromotionError",
    "ModelPromotionCancelInput",
    "ModelPromotionCreateInput",
    "ModelPromotionNotFoundError",
    "ModelPromotionPersistenceError",
    "ModelPromotionReviewInput",
    "ModelPromotionService",
    "ModelPromotionServiceError",
    "ModelPromotionStateConflictError",
    "NonWinningResultRequiresOverrideError",
]
