"""Deployment-candidate lifecycle orchestration without deployment execution."""

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.db.mixins import utc_now
from app.models import DeploymentCandidate, DeploymentCandidateStatus, DeploymentCandidateStatusHistory, ModelPromotionStatus
from app.repositories import DeploymentCandidateRepository, DeploymentCandidateStatusHistoryRepository, ModelPromotionRepository


class DeploymentCandidateServiceError(Exception): pass
class DeploymentCandidateNotFoundError(DeploymentCandidateServiceError): pass
class PromotionDecisionNotFoundForCandidateError(DeploymentCandidateServiceError): pass
class PromotionDecisionNotApprovedError(DeploymentCandidateServiceError): pass
class DuplicateDeploymentCandidateError(DeploymentCandidateServiceError): pass
class InvalidDeploymentCandidateError(DeploymentCandidateServiceError): pass
class DeploymentCandidateConsistencyError(DeploymentCandidateServiceError): pass
class DeploymentCandidateStateConflictError(DeploymentCandidateServiceError): pass
class ActiveDeploymentCandidateConflictError(DeploymentCandidateServiceError): pass
class DeploymentCandidatePersistenceError(DeploymentCandidateServiceError): pass


@dataclass(frozen=True, slots=True)
class DeploymentCandidateCreateInput:
    model_promotion_decision_id: UUID
    registered_by_user_id: UUID
    notes: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentCandidateStageInput:
    candidate_id: UUID
    staged_by_user_id: UUID
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentCandidateActivateInput:
    candidate_id: UUID
    activated_by_user_id: UUID
    note: str | None = None


@dataclass(frozen=True, slots=True)
class DeploymentCandidateRetireInput:
    candidate_id: UUID
    retired_by_user_id: UUID
    retirement_reason: str


@dataclass(frozen=True, slots=True)
class DeploymentCandidateRejectInput:
    candidate_id: UUID
    rejected_by_user_id: UUID
    rejection_reason: str


_INVALID = "Deployment candidate data is invalid."
_MAX_TEXT = 10_000
_REPLACED = "Replaced by another active deployment candidate."


class DeploymentCandidateService:
    def __init__(self, candidate_repository: DeploymentCandidateRepository, promotion_repository: ModelPromotionRepository, history_repository: DeploymentCandidateStatusHistoryRepository) -> None:
        self._candidates = candidate_repository
        self._promotions = promotion_repository
        self._history = history_repository

    async def create_candidate(self, value: DeploymentCandidateCreateInput) -> DeploymentCandidate:
        if not isinstance(value, DeploymentCandidateCreateInput): raise InvalidDeploymentCandidateError(_INVALID)
        self._uuids(value.model_promotion_decision_id, value.registered_by_user_id)
        notes = self._optional_text(value.notes)
        promotion = await self._promotions.get_with_details(value.model_promotion_decision_id)
        if promotion is None: raise PromotionDecisionNotFoundForCandidateError("Promotion decision was not found.")
        self._validate_promotion(promotion)
        if await self._candidates.get_for_promotion(promotion.id) is not None:
            raise DuplicateDeploymentCandidateError("A deployment candidate already exists for this promotion.")
        candidate = DeploymentCandidate(
            id=uuid4(),
            model_promotion_decision_id=promotion.id,
            benchmark_result_id=promotion.selected_benchmark_result_id,
            model_version_id=promotion.selected_model_version_id,
            status=DeploymentCandidateStatus.CANDIDATE,
            registered_by_user_id=value.registered_by_user_id,
            registered_at=utc_now(), staged_at=None, activated_at=None,
            retired_at=None, retirement_reason=None, notes=notes,
        )
        history = self._history_row(candidate, None, DeploymentCandidateStatus.CANDIDATE, value.registered_by_user_id, notes, candidate.registered_at)
        return await self._persist_new(candidate, history)

    async def stage_candidate(self, value: DeploymentCandidateStageInput) -> DeploymentCandidate:
        if not isinstance(value, DeploymentCandidateStageInput): raise InvalidDeploymentCandidateError(_INVALID)
        self._uuids(value.candidate_id, value.staged_by_user_id); notes = self._optional_text(value.note)
        candidate = await self._load(value.candidate_id)
        self._require_status(candidate, DeploymentCandidateStatus.CANDIDATE)
        self._validate_consistency(candidate)
        candidate.status = DeploymentCandidateStatus.STAGED; candidate.staged_at = utc_now()
        if notes is not None: candidate.notes = notes
        history = self._history_row(candidate, DeploymentCandidateStatus.CANDIDATE, DeploymentCandidateStatus.STAGED, value.staged_by_user_id, notes, candidate.staged_at)
        return await self._flush_reload(candidate, history)

    async def activate_candidate(self, value: DeploymentCandidateActivateInput) -> DeploymentCandidate:
        if not isinstance(value, DeploymentCandidateActivateInput): raise InvalidDeploymentCandidateError(_INVALID)
        self._uuids(value.candidate_id, value.activated_by_user_id); notes = self._optional_text(value.note)
        candidate = await self._load(value.candidate_id)
        self._require_status(candidate, DeploymentCandidateStatus.STAGED)
        self._validate_consistency(candidate)
        active = await self._candidates.get_active_candidate()
        now = utc_now()
        if active is not None and active.id != candidate.id:
            self._validate_consistency(active)
            active.status = DeploymentCandidateStatus.RETIRED
            active.retired_at = now
            active.retirement_reason = _REPLACED
            replacement_history = self._history_row(active, DeploymentCandidateStatus.ACTIVE, DeploymentCandidateStatus.RETIRED, value.activated_by_user_id, _REPLACED, now)
        else:
            replacement_history = None
        candidate.status = DeploymentCandidateStatus.ACTIVE; candidate.activated_at = now
        if notes is not None: candidate.notes = notes
        activation_history = self._history_row(candidate, DeploymentCandidateStatus.STAGED, DeploymentCandidateStatus.ACTIVE, value.activated_by_user_id, notes, now)
        histories = [activation_history] if replacement_history is None else [replacement_history, activation_history]
        return await self._flush_reload(candidate, *histories)

    async def retire_candidate(self, value: DeploymentCandidateRetireInput) -> DeploymentCandidate:
        if not isinstance(value, DeploymentCandidateRetireInput): raise InvalidDeploymentCandidateError(_INVALID)
        self._uuids(value.candidate_id, value.retired_by_user_id); reason = self._required_text(value.retirement_reason)
        candidate = await self._load(value.candidate_id)
        if candidate.status not in (DeploymentCandidateStatus.STAGED, DeploymentCandidateStatus.ACTIVE):
            raise DeploymentCandidateStateConflictError("Deployment candidate cannot be retired from its current state.")
        self._validate_consistency(candidate)
        previous_status = candidate.status
        candidate.status = DeploymentCandidateStatus.RETIRED; candidate.retired_at = utc_now(); candidate.retirement_reason = reason
        history = self._history_row(candidate, previous_status, DeploymentCandidateStatus.RETIRED, value.retired_by_user_id, reason, candidate.retired_at)
        return await self._flush_reload(candidate, history)

    async def reject_candidate(self, value: DeploymentCandidateRejectInput) -> DeploymentCandidate:
        if not isinstance(value, DeploymentCandidateRejectInput): raise InvalidDeploymentCandidateError(_INVALID)
        self._uuids(value.candidate_id, value.rejected_by_user_id); reason = self._required_text(value.rejection_reason)
        candidate = await self._load(value.candidate_id)
        if candidate.status not in (DeploymentCandidateStatus.CANDIDATE, DeploymentCandidateStatus.STAGED):
            raise DeploymentCandidateStateConflictError("Deployment candidate cannot be rejected from its current state.")
        self._validate_consistency(candidate)
        previous_status = candidate.status
        candidate.status = DeploymentCandidateStatus.REJECTED; candidate.retired_at = utc_now(); candidate.retirement_reason = reason
        history = self._history_row(candidate, previous_status, DeploymentCandidateStatus.REJECTED, value.rejected_by_user_id, reason, candidate.retired_at)
        return await self._flush_reload(candidate, history)

    async def get_candidate(self, candidate_id: UUID) -> DeploymentCandidate:
        self._uuids(candidate_id); return await self._load(candidate_id)

    async def get_active_candidate(self) -> DeploymentCandidate | None:
        return await self._candidates.get_active_candidate()

    async def list_candidates(self, *, status: DeploymentCandidateStatus | None = None, offset: int = 0, limit: int = 100) -> list[DeploymentCandidate]:
        return await self._candidates.list_candidates(status=status, offset=offset, limit=limit)

    async def list_candidate_history(self, candidate_id: UUID, *, offset: int = 0, limit: int = 100) -> list[DeploymentCandidateStatusHistory]:
        self._uuids(candidate_id)
        await self._load(candidate_id)
        return await self._history.list_for_candidate(candidate_id, offset=offset, limit=limit)

    async def get_latest_candidate_history(self, candidate_id: UUID) -> DeploymentCandidateStatusHistory | None:
        self._uuids(candidate_id)
        await self._load(candidate_id)
        return await self._history.get_latest_for_candidate(candidate_id)

    async def _load(self, candidate_id: UUID) -> DeploymentCandidate:
        candidate = await self._candidates.get_with_details(candidate_id)
        if candidate is None: raise DeploymentCandidateNotFoundError("Deployment candidate was not found.")
        return candidate

    async def _persist_new(self, candidate: DeploymentCandidate, history: DeploymentCandidateStatusHistory) -> DeploymentCandidate:
        try:
            await self._candidates.add_candidate(candidate); await self._history.add_history(history); await self._candidates.flush()
            complete = await self._candidates.get_with_details(candidate.id)
        except IntegrityError as error:
            constraint = getattr(getattr(error.orig, "diag", None), "constraint_name", None)
            if constraint == "uq_deployment_candidates_promotion_id":
                raise DuplicateDeploymentCandidateError("A deployment candidate already exists for this promotion.") from None
            raise DeploymentCandidatePersistenceError("Deployment candidate could not be persisted.") from None
        except Exception:
            raise DeploymentCandidatePersistenceError("Deployment candidate could not be persisted.") from None
        if complete is None: raise DeploymentCandidatePersistenceError("Deployment candidate could not be persisted.")
        return complete

    async def _flush_reload(self, candidate: DeploymentCandidate, *histories: DeploymentCandidateStatusHistory) -> DeploymentCandidate:
        try:
            for history in histories: await self._history.add_history(history)
            await self._candidates.flush(); complete = await self._candidates.get_with_details(candidate.id)
        except Exception:
            raise DeploymentCandidatePersistenceError("Deployment candidate could not be persisted.") from None
        if complete is None: raise DeploymentCandidatePersistenceError("Deployment candidate could not be persisted.")
        return complete

    @staticmethod
    def _history_row(candidate, previous_status, new_status, actor_id, note, changed_at) -> DeploymentCandidateStatusHistory:
        return DeploymentCandidateStatusHistory(
            deployment_candidate_id=candidate.id,
            previous_status=previous_status,
            new_status=new_status,
            changed_by_user_id=actor_id,
            note=note,
            changed_at=changed_at,
        )

    @staticmethod
    def _validate_promotion(promotion) -> None:
        if promotion.status is not ModelPromotionStatus.APPROVED:
            raise PromotionDecisionNotApprovedError("Promotion decision is not approved.")
        if (promotion.selected_benchmark_result is None or promotion.selected_model_version is None
            or promotion.selected_benchmark_result.id != promotion.selected_benchmark_result_id
            or promotion.selected_benchmark_result.model_version_id != promotion.selected_model_version_id
            or promotion.selected_model_version.id != promotion.selected_model_version_id):
            raise DeploymentCandidateConsistencyError("Promotion decision selections are inconsistent.")

    @classmethod
    def _validate_consistency(cls, candidate) -> None:
        promotion = candidate.model_promotion_decision
        if promotion is None: raise DeploymentCandidateConsistencyError("Deployment candidate references are inconsistent.")
        cls._validate_promotion(promotion)
        if (candidate.benchmark_result is None or candidate.model_version is None
            or candidate.benchmark_result_id != promotion.selected_benchmark_result_id
            or candidate.model_version_id != promotion.selected_model_version_id
            or candidate.benchmark_result.id != candidate.benchmark_result_id
            or candidate.benchmark_result.model_version_id != candidate.model_version_id
            or candidate.model_version.id != candidate.model_version_id):
            raise DeploymentCandidateConsistencyError("Deployment candidate references are inconsistent.")

    @staticmethod
    def _require_status(candidate, expected: DeploymentCandidateStatus) -> None:
        if candidate.status is not expected: raise DeploymentCandidateStateConflictError("Deployment candidate state does not allow this operation.")

    @staticmethod
    def _uuids(*values) -> None:
        if any(not isinstance(value, UUID) for value in values): raise InvalidDeploymentCandidateError(_INVALID)

    @staticmethod
    def _required_text(value) -> str:
        if not isinstance(value, str): raise InvalidDeploymentCandidateError(_INVALID)
        normalized = value.strip()
        if not normalized or len(normalized) > _MAX_TEXT: raise InvalidDeploymentCandidateError(_INVALID)
        return normalized

    @classmethod
    def _optional_text(cls, value) -> str | None:
        return None if value is None else cls._required_text(value)


__all__ = [
    "ActiveDeploymentCandidateConflictError", "DeploymentCandidateActivateInput", "DeploymentCandidateConsistencyError",
    "DeploymentCandidateCreateInput", "DeploymentCandidateNotFoundError",
    "DeploymentCandidatePersistenceError", "DeploymentCandidateRejectInput",
    "DeploymentCandidateRetireInput", "DeploymentCandidateService",
    "DeploymentCandidateServiceError", "DeploymentCandidateStageInput",
    "DeploymentCandidateStateConflictError", "DuplicateDeploymentCandidateError",
    "InvalidDeploymentCandidateError", "PromotionDecisionNotApprovedError",
    "PromotionDecisionNotFoundForCandidateError",
]
