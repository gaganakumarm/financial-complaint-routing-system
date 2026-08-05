"""Deployment candidate service tests."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
import pytest
from app.models import DeploymentCandidateStatus, ModelPromotionStatus
from app.services import DeploymentCandidateActivateInput, DeploymentCandidateConsistencyError, DeploymentCandidateCreateInput, DeploymentCandidateNotFoundError, DeploymentCandidatePersistenceError, DeploymentCandidateRejectInput, DeploymentCandidateRetireInput, DeploymentCandidateService, DeploymentCandidateStageInput, DeploymentCandidateStateConflictError, DuplicateDeploymentCandidateError, InvalidDeploymentCandidateError, PromotionDecisionNotApprovedError, PromotionDecisionNotFoundForCandidateError


def repositories():
    candidates = MagicMock(); promotions = MagicMock(); history = MagicMock()
    for name, default in (("get_for_promotion", None), ("get_with_details", None), ("get_active_candidate", None)):
        setattr(candidates, name, AsyncMock(return_value=default))
    candidates.add_candidate = AsyncMock(); candidates.flush = AsyncMock(); candidates.list_candidates = AsyncMock(return_value=[])
    candidates.commit = AsyncMock(); candidates.rollback = AsyncMock(); candidates.begin = AsyncMock()
    history.add_history = AsyncMock(); history.list_for_candidate = AsyncMock(return_value=[]); history.get_latest_for_candidate = AsyncMock(return_value=None)
    history.commit = AsyncMock(); history.rollback = AsyncMock(); history.begin = AsyncMock()
    promotions.get_with_details = AsyncMock(); return candidates, promotions, history


def promotion(*, status=ModelPromotionStatus.APPROVED, consistent=True):
    result_id, model_id = uuid4(), uuid4()
    result = SimpleNamespace(id=result_id, model_version_id=model_id)
    model = SimpleNamespace(id=model_id if consistent else uuid4())
    return SimpleNamespace(id=uuid4(), status=status, selected_benchmark_result_id=result_id, selected_model_version_id=model_id, selected_benchmark_result=result, selected_model_version=model)


def candidate(*, status=DeploymentCandidateStatus.CANDIDATE, consistent=True):
    promo = promotion(consistent=consistent)
    result = SimpleNamespace(id=promo.selected_benchmark_result_id, model_version_id=promo.selected_model_version_id)
    return SimpleNamespace(id=uuid4(), model_promotion_decision_id=promo.id, benchmark_result_id=result.id, model_version_id=promo.selected_model_version_id, status=status, registered_by_user_id=uuid4(), registered_at=SimpleNamespace(), staged_at=None, activated_at=None, retired_at=None, retirement_reason=None, notes=None, model_promotion_decision=promo, benchmark_result=result, model_version=SimpleNamespace(id=promo.selected_model_version_id))


def no_writes(repo): repo.add_candidate.assert_not_awaited(); repo.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_create_derives_approved_promotion_selections_and_is_neutral() -> None:
    candidates, promotions, history = repositories(); promo = promotion(); promotions.get_with_details.return_value = promo; complete = object(); candidates.get_with_details.return_value = complete
    service = DeploymentCandidateService(candidates, promotions, history); user_id = uuid4()
    assert await service.create_candidate(DeploymentCandidateCreateInput(promo.id, user_id, "  notes  ")) is complete
    persisted = candidates.add_candidate.await_args.args[0]
    assert (persisted.benchmark_result_id, persisted.model_version_id, persisted.registered_by_user_id) == (promo.selected_benchmark_result_id, promo.selected_model_version_id, user_id)
    assert persisted.status is DeploymentCandidateStatus.CANDIDATE and persisted.notes == "notes"
    event = history.add_history.await_args.args[0]
    assert event.previous_status is None and event.new_status is DeploymentCandidateStatus.CANDIDATE
    assert event.changed_by_user_id == user_id and event.note == "notes" and event.changed_at is persisted.registered_at
    candidates.flush.assert_awaited_once(); candidates.commit.assert_not_awaited(); candidates.rollback.assert_not_awaited(); candidates.begin.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("case,error", [("missing", PromotionDecisionNotFoundForCandidateError), ("unapproved", PromotionDecisionNotApprovedError), ("inconsistent", DeploymentCandidateConsistencyError), ("duplicate", DuplicateDeploymentCandidateError)])
async def test_create_validation_before_writes(case, error) -> None:
    candidates, promotions, history = repositories(); promo = promotion(status=ModelPromotionStatus.PENDING if case == "unapproved" else ModelPromotionStatus.APPROVED, consistent=case != "inconsistent")
    promotions.get_with_details.return_value = None if case == "missing" else promo
    if case == "duplicate": candidates.get_for_promotion.return_value = object()
    with pytest.raises(error): await DeploymentCandidateService(candidates, promotions, history).create_candidate(DeploymentCandidateCreateInput(promo.id, uuid4()))
    no_writes(candidates); history.add_history.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("value", ["bad", True])
async def test_invalid_create_uuid_is_rejected_without_reads(value) -> None:
    candidates, promotions, history = repositories()
    with pytest.raises(InvalidDeploymentCandidateError): await DeploymentCandidateService(candidates, promotions, history).create_candidate(DeploymentCandidateCreateInput(value, uuid4()))
    promotions.get_with_details.assert_not_awaited(); no_writes(candidates)


@pytest.mark.anyio
async def test_stage_candidate() -> None:
    candidates, promotions, history = repositories(); item = candidate(); candidates.get_with_details.side_effect = [item, item]
    actor_id = uuid4()
    returned = await DeploymentCandidateService(candidates, promotions, history).stage_candidate(DeploymentCandidateStageInput(item.id, actor_id, " staged "))
    assert returned.status is DeploymentCandidateStatus.STAGED and returned.staged_at is not None and returned.notes == "staged"
    candidates.flush.assert_awaited_once()
    event = history.add_history.await_args.args[0]
    assert (event.previous_status, event.new_status, event.changed_by_user_id, event.note) == (DeploymentCandidateStatus.CANDIDATE, DeploymentCandidateStatus.STAGED, actor_id, "staged")
    assert event.changed_at is item.staged_at


@pytest.mark.anyio
async def test_activate_retires_existing_active_in_same_flush() -> None:
    candidates, promotions, history = repositories(); item = candidate(status=DeploymentCandidateStatus.STAGED); item.staged_at = SimpleNamespace(); active = candidate(status=DeploymentCandidateStatus.ACTIVE); active.staged_at = active.activated_at = SimpleNamespace()
    candidates.get_with_details.side_effect = [item, item]; candidates.get_active_candidate.return_value = active
    actor_id = uuid4(); returned = await DeploymentCandidateService(candidates, promotions, history).activate_candidate(DeploymentCandidateActivateInput(item.id, actor_id, " activation "))
    assert returned.status is DeploymentCandidateStatus.ACTIVE and returned.activated_at is not None
    assert active.status is DeploymentCandidateStatus.RETIRED and active.retired_at is not None and "Replaced" in active.retirement_reason
    candidates.flush.assert_awaited_once()
    replacement, activation = [call.args[0] for call in history.add_history.await_args_list]
    assert (replacement.previous_status, replacement.new_status, replacement.changed_by_user_id, replacement.note) == (DeploymentCandidateStatus.ACTIVE, DeploymentCandidateStatus.RETIRED, actor_id, "Replaced by another active deployment candidate.")
    assert (activation.previous_status, activation.new_status, activation.changed_by_user_id, activation.note) == (DeploymentCandidateStatus.STAGED, DeploymentCandidateStatus.ACTIVE, actor_id, "activation")
    assert replacement.changed_at is activation.changed_at is item.activated_at is active.retired_at


@pytest.mark.anyio
async def test_activate_without_replacement_adds_one_history_and_flushes_once() -> None:
    candidates, promotions, history = repositories(); item = candidate(status=DeploymentCandidateStatus.STAGED); item.staged_at = SimpleNamespace()
    candidates.get_with_details.side_effect = [item, item]; actor_id = uuid4()
    await DeploymentCandidateService(candidates, promotions, history).activate_candidate(DeploymentCandidateActivateInput(item.id, actor_id))
    history.add_history.assert_awaited_once()
    event = history.add_history.await_args.args[0]
    assert (event.previous_status, event.new_status, event.changed_by_user_id, event.note) == (DeploymentCandidateStatus.STAGED, DeploymentCandidateStatus.ACTIVE, actor_id, None)
    assert event.changed_at is item.activated_at
    candidates.flush.assert_awaited_once()


@pytest.mark.anyio
async def test_retire_and_reject_store_normalized_reasons() -> None:
    for method, dto, start, target in (("retire_candidate", DeploymentCandidateRetireInput, DeploymentCandidateStatus.ACTIVE, DeploymentCandidateStatus.RETIRED), ("reject_candidate", DeploymentCandidateRejectInput, DeploymentCandidateStatus.CANDIDATE, DeploymentCandidateStatus.REJECTED)):
        candidates, promotions, history = repositories(); item = candidate(status=start); candidates.get_with_details.side_effect = [item, item]; actor_id = uuid4()
        returned = await getattr(DeploymentCandidateService(candidates, promotions, history), method)(dto(item.id, actor_id, "  reason  "))
        assert returned.status is target and returned.retirement_reason == "reason" and returned.retired_at is not None
        candidates.flush.assert_awaited_once()
        event = history.add_history.await_args.args[0]
        assert event.previous_status is start and event.new_status is target and event.changed_by_user_id == actor_id and event.note == "reason"
        assert event.changed_at is item.retired_at


@pytest.mark.anyio
async def test_invalid_transitions_and_consistency_do_not_mutate() -> None:
    candidates, promotions, history = repositories(); item = candidate(status=DeploymentCandidateStatus.ACTIVE); candidates.get_with_details.return_value = item; original = dict(item.__dict__)
    with pytest.raises(DeploymentCandidateStateConflictError): await DeploymentCandidateService(candidates, promotions, history).stage_candidate(DeploymentCandidateStageInput(item.id, uuid4()))
    assert item.__dict__ == original; candidates.flush.assert_not_awaited()
    history.add_history.assert_not_awaited()
    candidates, promotions, history = repositories(); item = candidate(consistent=False); candidates.get_with_details.return_value = item
    with pytest.raises(DeploymentCandidateConsistencyError): await DeploymentCandidateService(candidates, promotions, history).stage_candidate(DeploymentCandidateStageInput(item.id, uuid4()))
    candidates.flush.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("method,dto,actor_field", [
    ("stage_candidate", DeploymentCandidateStageInput, "staged_by_user_id"),
    ("activate_candidate", DeploymentCandidateActivateInput, "activated_by_user_id"),
    ("retire_candidate", DeploymentCandidateRetireInput, "retired_by_user_id"),
    ("reject_candidate", DeploymentCandidateRejectInput, "rejected_by_user_id"),
])
@pytest.mark.parametrize("invalid_actor", ["not-a-uuid", True])
async def test_invalid_lifecycle_actor_is_rejected_before_repository_access(method, dto, actor_field, invalid_actor) -> None:
    candidates, promotions, history = repositories(); service = DeploymentCandidateService(candidates, promotions, history)
    values = {"candidate_id": uuid4(), actor_field: invalid_actor}
    if dto is DeploymentCandidateRetireInput:
        values["retirement_reason"] = "reason"
    elif dto is DeploymentCandidateRejectInput:
        values["rejection_reason"] = "reason"
    else:
        values["note"] = None
    with pytest.raises(InvalidDeploymentCandidateError):
        await getattr(service, method)(dto(**values))
    candidates.get_with_details.assert_not_awaited()
    candidates.get_active_candidate.assert_not_awaited()
    no_writes(candidates)
    history.add_history.assert_not_awaited()


@pytest.mark.anyio
async def test_missing_reads_and_list_active_delegate_without_writes() -> None:
    candidates, promotions, history = repositories(); service = DeploymentCandidateService(candidates, promotions, history); identifier = uuid4()
    with pytest.raises(DeploymentCandidateNotFoundError): await service.get_candidate(identifier)
    active = candidate(status=DeploymentCandidateStatus.ACTIVE); candidates.get_active_candidate.return_value = active
    assert await service.get_active_candidate() is active
    assert await service.list_candidates(status=DeploymentCandidateStatus.RETIRED, offset=2, limit=7) == []
    candidates.list_candidates.assert_awaited_once_with(status=DeploymentCandidateStatus.RETIRED, offset=2, limit=7); no_writes(candidates)


@pytest.mark.anyio
async def test_history_reads_require_candidate_and_never_write() -> None:
    candidates, promotions, history = repositories(); service = DeploymentCandidateService(candidates, promotions, history); identifier = uuid4(); item = candidate()
    candidates.get_with_details.side_effect = [item, item, None]
    event = object(); history.list_for_candidate.return_value = [event]; history.get_latest_for_candidate.return_value = event
    assert await service.list_candidate_history(identifier, offset=2, limit=7) == [event]
    assert await service.get_latest_candidate_history(identifier) is event
    history.list_for_candidate.assert_awaited_once_with(identifier, offset=2, limit=7)
    history.get_latest_for_candidate.assert_awaited_once_with(identifier)
    with pytest.raises(DeploymentCandidateNotFoundError): await service.list_candidate_history(identifier)
    history.add_history.assert_not_awaited(); candidates.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_cancelled_error_propagates() -> None:
    candidates, promotions, history = repositories(); promo = promotion(); promotions.get_with_details.return_value = promo; candidates.flush.side_effect = asyncio.CancelledError()
    with pytest.raises(asyncio.CancelledError): await DeploymentCandidateService(candidates, promotions, history).create_candidate(DeploymentCandidateCreateInput(promo.id, uuid4()))


@pytest.mark.anyio
async def test_history_persistence_failure_is_safely_translated() -> None:
    candidates, promotions, history = repositories(); item = candidate(); candidates.get_with_details.return_value = item
    history.add_history.side_effect = RuntimeError("driver detail")
    with pytest.raises(DeploymentCandidatePersistenceError, match="could not be persisted") as caught:
        await DeploymentCandidateService(candidates, promotions, history).stage_candidate(DeploymentCandidateStageInput(item.id, uuid4()))
    assert "driver detail" not in str(caught.value)
    candidates.flush.assert_not_awaited()
