"""Deployment-candidate workflow REST API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import DeploymentCandidateServiceDependency, TransactionalDeploymentCandidateServiceDependency
from app.authz import AdministratorUser, ReviewerOrAdministratorUser
from app.models import DeploymentCandidateStatus
from app.schemas import (
    DeploymentCandidateActivateRequest, DeploymentCandidateCreateRequest,
    DeploymentCandidateListResponse, DeploymentCandidateRejectRequest,
    DeploymentCandidateResponse, DeploymentCandidateRetireRequest,
    DeploymentCandidateStageRequest,
    DeploymentCandidateStatusHistoryListResponse,
    DeploymentCandidateStatusHistoryResponse,
)
from app.services import (
    DeploymentCandidateActivateInput, DeploymentCandidateConsistencyError,
    DeploymentCandidateCreateInput, DeploymentCandidateNotFoundError,
    DeploymentCandidatePersistenceError, DeploymentCandidateRejectInput,
    DeploymentCandidateRetireInput, DeploymentCandidateStageInput,
    DeploymentCandidateStateConflictError, DuplicateDeploymentCandidateError,
    InvalidDeploymentCandidateError, PromotionDecisionNotApprovedError,
    PromotionDecisionNotFoundForCandidateError,
)
from app.services.deployment_candidate import ActiveDeploymentCandidateConflictError

router = APIRouter(prefix="/deployment-candidates", tags=["Deployment Candidates"])

_SERVICE_ERRORS = (
    DeploymentCandidateNotFoundError, PromotionDecisionNotFoundForCandidateError,
    ActiveDeploymentCandidateConflictError,
    PromotionDecisionNotApprovedError, DuplicateDeploymentCandidateError,
    DeploymentCandidateConsistencyError, DeploymentCandidateStateConflictError,
    InvalidDeploymentCandidateError, DeploymentCandidatePersistenceError,
)


def _translate_error(error: Exception) -> HTTPException:
    mappings = (
        (DeploymentCandidateNotFoundError, 404, "Deployment candidate not found"),
        (PromotionDecisionNotFoundForCandidateError, 404, "Model promotion not found"),
        (PromotionDecisionNotApprovedError, 409, "Model promotion is not approved"),
        (DuplicateDeploymentCandidateError, 409, "A deployment candidate already exists for this promotion"),
        (DeploymentCandidateConsistencyError, 409, "Deployment candidate data is inconsistent"),
        (DeploymentCandidateStateConflictError, 409, "Deployment candidate state does not allow this operation"),
        (ActiveDeploymentCandidateConflictError, 409, "Another deployment candidate is already active"),
        (InvalidDeploymentCandidateError, 422, "Invalid deployment candidate"),
        (DeploymentCandidatePersistenceError, 500, "Deployment candidate could not be persisted"),
    )
    for error_type, status_code, detail in mappings:
        if isinstance(error, error_type):
            return HTTPException(status_code=status_code, detail=detail)
    raise error


def _response(candidate) -> DeploymentCandidateResponse:
    return DeploymentCandidateResponse.model_validate(candidate)


@router.post("", response_model=DeploymentCandidateResponse, status_code=status.HTTP_201_CREATED)
async def create_deployment_candidate(payload: DeploymentCandidateCreateRequest, current_user: AdministratorUser, candidate_service: TransactionalDeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    try:
        candidate = await candidate_service.create_candidate(DeploymentCandidateCreateInput(model_promotion_decision_id=payload.model_promotion_decision_id, registered_by_user_id=current_user.id, notes=payload.notes))
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    return _response(candidate)


@router.get("/active", response_model=DeploymentCandidateResponse)
async def get_active_deployment_candidate(current_user: ReviewerOrAdministratorUser, candidate_service: DeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    del current_user
    candidate = await candidate_service.get_active_candidate()
    if candidate is None:
        raise HTTPException(status_code=404, detail="Active deployment candidate not found")
    return _response(candidate)


@router.get("/{candidate_id}/history/latest", response_model=DeploymentCandidateStatusHistoryResponse)
async def get_latest_deployment_candidate_history(candidate_id: UUID, current_user: ReviewerOrAdministratorUser, candidate_service: DeploymentCandidateServiceDependency) -> DeploymentCandidateStatusHistoryResponse:
    del current_user
    try:
        history = await candidate_service.get_latest_candidate_history(candidate_id)
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    if history is None:
        raise HTTPException(status_code=404, detail="Deployment candidate history not found")
    return DeploymentCandidateStatusHistoryResponse.model_validate(history)


@router.get("/{candidate_id}/history", response_model=DeploymentCandidateStatusHistoryListResponse)
async def list_deployment_candidate_history(candidate_id: UUID, current_user: ReviewerOrAdministratorUser, candidate_service: DeploymentCandidateServiceDependency, offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)) -> DeploymentCandidateStatusHistoryListResponse:
    del current_user
    try:
        history = await candidate_service.list_candidate_history(candidate_id, offset=offset, limit=limit)
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None
    return DeploymentCandidateStatusHistoryListResponse(
        items=[DeploymentCandidateStatusHistoryResponse.model_validate(item) for item in history],
        offset=offset,
        limit=limit,
        count=len(history),
    )


@router.get("/{candidate_id}", response_model=DeploymentCandidateResponse)
async def get_deployment_candidate(candidate_id: UUID, current_user: ReviewerOrAdministratorUser, candidate_service: DeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    del current_user
    try:
        return _response(await candidate_service.get_candidate(candidate_id))
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None


@router.get("", response_model=DeploymentCandidateListResponse)
async def list_deployment_candidates(current_user: ReviewerOrAdministratorUser, candidate_service: DeploymentCandidateServiceDependency, status_filter: DeploymentCandidateStatus | None = Query(default=None, alias="status"), offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500)) -> DeploymentCandidateListResponse:
    del current_user
    items = await candidate_service.list_candidates(status=status_filter, offset=offset, limit=limit)
    return DeploymentCandidateListResponse(items=[_response(item) for item in items], offset=offset, limit=limit, count=len(items))


async def _transition(candidate_id: UUID, value, candidate_service, method: str) -> DeploymentCandidateResponse:
    try:
        return _response(await getattr(candidate_service, method)(value))
    except _SERVICE_ERRORS as error:
        raise _translate_error(error) from None


@router.post("/{candidate_id}/stage", response_model=DeploymentCandidateResponse)
async def stage_deployment_candidate(candidate_id: UUID, payload: DeploymentCandidateStageRequest, current_user: AdministratorUser, candidate_service: TransactionalDeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    return await _transition(candidate_id, DeploymentCandidateStageInput(candidate_id=candidate_id, staged_by_user_id=current_user.id, note=payload.note), candidate_service, "stage_candidate")


@router.post("/{candidate_id}/activate", response_model=DeploymentCandidateResponse)
async def activate_deployment_candidate(candidate_id: UUID, payload: DeploymentCandidateActivateRequest, current_user: AdministratorUser, candidate_service: TransactionalDeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    return await _transition(candidate_id, DeploymentCandidateActivateInput(candidate_id=candidate_id, activated_by_user_id=current_user.id, note=payload.note), candidate_service, "activate_candidate")


@router.post("/{candidate_id}/retire", response_model=DeploymentCandidateResponse)
async def retire_deployment_candidate(candidate_id: UUID, payload: DeploymentCandidateRetireRequest, current_user: AdministratorUser, candidate_service: TransactionalDeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    return await _transition(candidate_id, DeploymentCandidateRetireInput(candidate_id=candidate_id, retired_by_user_id=current_user.id, retirement_reason=payload.retirement_reason), candidate_service, "retire_candidate")


@router.post("/{candidate_id}/reject", response_model=DeploymentCandidateResponse)
async def reject_deployment_candidate(candidate_id: UUID, payload: DeploymentCandidateRejectRequest, current_user: AdministratorUser, candidate_service: TransactionalDeploymentCandidateServiceDependency) -> DeploymentCandidateResponse:
    return await _transition(candidate_id, DeploymentCandidateRejectInput(candidate_id=candidate_id, rejected_by_user_id=current_user.id, rejection_reason=payload.rejection_reason), candidate_service, "reject_candidate")
