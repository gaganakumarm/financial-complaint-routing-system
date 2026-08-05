"""Model promotion service tests."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import ModelPromotionDecision, ModelPromotionStatus
from app.services import (
    BenchmarkComparisonNotFoundForPromotionError,
    BenchmarkResultModelMismatchError,
    BenchmarkResultNotFoundForPromotionError,
    BenchmarkResultNotInComparisonError,
    DuplicatePendingModelPromotionError,
    InvalidModelPromotionError,
    ModelPromotionCancelInput,
    ModelPromotionCreateInput,
    ModelPromotionNotFoundError,
    ModelPromotionPersistenceError,
    ModelPromotionReviewInput,
    ModelPromotionService,
    ModelPromotionStateConflictError,
    NonWinningResultRequiresOverrideError,
)


def repositories():
    promotions = MagicMock(); comparisons = MagicMock()
    promotions.get_pending_for_comparison = AsyncMock(return_value=None)
    promotions.add_promotion = AsyncMock(); promotions.flush = AsyncMock()
    promotions.get_with_details = AsyncMock(); promotions.list_promotions = AsyncMock(return_value=[])
    promotions.commit = AsyncMock(); promotions.rollback = AsyncMock(); promotions.begin = AsyncMock()
    comparisons.get_with_members = AsyncMock()
    return promotions, comparisons


def comparison(*, winner=True, loaded=True, mismatch=False):
    comparison_id, result_id, model_id = uuid4(), uuid4(), uuid4()
    model = SimpleNamespace(id=uuid4() if mismatch else model_id) if loaded else None
    result = SimpleNamespace(id=result_id, model_version_id=model_id, model_version=model)
    member = SimpleNamespace(id=uuid4(), benchmark_result_id=result_id, benchmark_result=result if loaded else None, rank=1)
    value = SimpleNamespace(id=comparison_id, winner_result_id=result_id if winner else uuid4(), members=[member])
    return value, result


def create_input(value, result, **updates):
    fields = dict(benchmark_comparison_id=value.id, selected_benchmark_result_id=result.id, requested_by_user_id=uuid4(), rationale="  strong evidence  ", override_winner=False)
    fields.update(updates); return ModelPromotionCreateInput(**fields)


def decision(*, status=ModelPromotionStatus.PENDING, winner=True, override=False):
    comparison_value, result = comparison(winner=winner)
    promotion = SimpleNamespace(
        id=uuid4(), benchmark_comparison_id=comparison_value.id,
        selected_benchmark_result_id=result.id, selected_model_version_id=result.model_version_id,
        status=status, rationale="evidence", override_winner=override,
        requested_by_user_id=uuid4(), benchmark_comparison=comparison_value,
        selected_benchmark_result=result, selected_model_version=result.model_version,
        reviewed_by_user_id=None, reviewed_at=None, review_note=None,
    )
    return promotion


def no_writes(repository):
    repository.add_promotion.assert_not_awaited(); repository.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_winner_creation_derives_model_normalizes_override_and_is_neutral() -> None:
    promotions, comparisons = repositories(); value, selected = comparison()
    comparisons.get_with_members.return_value = value
    complete = object(); promotions.get_with_details.return_value = complete
    service = ModelPromotionService(promotions, comparisons)
    request = create_input(value, selected, override_winner=True)
    assert await service.create_promotion(request) is complete
    persisted = promotions.add_promotion.await_args.args[0]
    assert persisted.selected_model_version_id == selected.model_version_id
    assert persisted.status is ModelPromotionStatus.PENDING and persisted.override_winner is False
    assert persisted.rationale == "strong evidence" and persisted.requested_at is not None
    comparisons.get_with_members.assert_awaited_once_with(value.id)
    promotions.get_pending_for_comparison.assert_awaited_once_with(value.id)
    promotions.flush.assert_awaited_once(); promotions.get_with_details.assert_awaited_once_with(persisted.id)
    promotions.commit.assert_not_awaited(); promotions.rollback.assert_not_awaited(); promotions.begin.assert_not_awaited()


@pytest.mark.anyio
async def test_nonwinner_requires_explicit_override() -> None:
    for override, accepted in ((False, False), (True, True)):
        promotions, comparisons = repositories(); value, selected = comparison(winner=False)
        comparisons.get_with_members.return_value = value; promotions.get_with_details.return_value = object()
        service = ModelPromotionService(promotions, comparisons)
        if accepted:
            await service.create_promotion(create_input(value, selected, override_winner=override))
            assert promotions.add_promotion.await_args.args[0].override_winner is True
        else:
            with pytest.raises(NonWinningResultRequiresOverrideError): await service.create_promotion(create_input(value, selected))
            no_writes(promotions)


@pytest.mark.anyio
@pytest.mark.parametrize("case,error", [
    ("missing_comparison", BenchmarkComparisonNotFoundForPromotionError),
    ("outside", BenchmarkResultNotInComparisonError),
    ("missing_result", BenchmarkResultNotFoundForPromotionError),
    ("mismatch", BenchmarkResultModelMismatchError),
    ("duplicate", DuplicatePendingModelPromotionError),
])
async def test_create_cross_table_failures_write_nothing(case, error) -> None:
    promotions, comparisons = repositories(); value, selected = comparison(mismatch=case == "mismatch")
    comparisons.get_with_members.return_value = value
    request = create_input(value, selected)
    if case == "missing_comparison": comparisons.get_with_members.return_value = None
    elif case == "outside": request = create_input(value, selected, selected_benchmark_result_id=uuid4())
    elif case == "missing_result": value.members[0].benchmark_result = None
    elif case == "duplicate": promotions.get_pending_for_comparison.return_value = object()
    with pytest.raises(error): await ModelPromotionService(promotions, comparisons).create_promotion(request)
    no_writes(promotions)


@pytest.mark.anyio
@pytest.mark.parametrize("updates", [
    {"rationale": " "}, {"rationale": "x" * 10001}, {"override_winner": 1},
    {"benchmark_comparison_id": "bad"}, {"selected_benchmark_result_id": True},
    {"requested_by_user_id": "bad"},
])
async def test_invalid_create_input_has_no_repository_access(updates) -> None:
    promotions, comparisons = repositories(); value, selected = comparison(); data = create_input(value, selected, **updates)
    with pytest.raises(InvalidModelPromotionError): await ModelPromotionService(promotions, comparisons).create_promotion(data)
    comparisons.get_with_members.assert_not_awaited(); no_writes(promotions)


@pytest.mark.anyio
async def test_persistence_error_is_safe_and_cancelled_error_propagates() -> None:
    value, selected = comparison()
    for exception, expected in ((RuntimeError("secret SQL"), ModelPromotionPersistenceError), (asyncio.CancelledError(), asyncio.CancelledError)):
        promotions, comparisons = repositories(); comparisons.get_with_members.return_value = value
        promotions.flush.side_effect = exception
        with pytest.raises(expected) as caught: await ModelPromotionService(promotions, comparisons).create_promotion(create_input(value, selected))
        assert "secret" not in str(caught.value)


@pytest.mark.anyio
async def test_pending_uniqueness_race_is_translated_by_constraint_identity() -> None:
    value, selected = comparison(); promotions, comparisons = repositories()
    comparisons.get_with_members.return_value = value
    original = SimpleNamespace(diag=SimpleNamespace(constraint_name="uq_model_promotion_decisions_pending_comparison"))
    promotions.flush.side_effect = IntegrityError("statement", {}, original)
    with pytest.raises(DuplicatePendingModelPromotionError):
        await ModelPromotionService(promotions, comparisons).create_promotion(create_input(value, selected))


@pytest.mark.anyio
@pytest.mark.parametrize("method,target", [("approve_promotion", ModelPromotionStatus.APPROVED), ("reject_promotion", ModelPromotionStatus.REJECTED)])
async def test_review_transitions_store_attribution_and_normalized_note(method, target) -> None:
    promotions, comparisons = repositories(); promotion = decision(); promotions.get_with_details.side_effect = [promotion, promotion]
    reviewer = uuid4(); request = ModelPromotionReviewInput(promotion.id, reviewer, "  reviewed  ")
    returned = await getattr(ModelPromotionService(promotions, comparisons), method)(request)
    assert returned is promotion and promotion.status is target
    assert promotion.reviewed_by_user_id == reviewer and promotion.review_note == "reviewed" and promotion.reviewed_at is not None
    promotions.flush.assert_awaited_once()


@pytest.mark.anyio
@pytest.mark.parametrize("status", [ModelPromotionStatus.APPROVED, ModelPromotionStatus.REJECTED, ModelPromotionStatus.CANCELLED])
async def test_terminal_decisions_cannot_transition(status) -> None:
    promotions, comparisons = repositories(); promotion = decision(status=status); promotions.get_with_details.return_value = promotion
    original = dict(promotion.__dict__)
    with pytest.raises(ModelPromotionStateConflictError): await ModelPromotionService(promotions, comparisons).approve_promotion(ModelPromotionReviewInput(promotion.id, uuid4(), "note"))
    assert promotion.__dict__ == original; promotions.flush.assert_not_awaited()


@pytest.mark.anyio
@pytest.mark.parametrize("defect,error", [("member", BenchmarkResultNotInComparisonError), ("model", BenchmarkResultModelMismatchError), ("override", NonWinningResultRequiresOverrideError)])
async def test_approval_revalidates_consistency_before_mutation(defect, error) -> None:
    promotions, comparisons = repositories(); promotion = decision()
    if defect == "member": promotion.benchmark_comparison.members = []
    elif defect == "model": promotion.selected_model_version_id = uuid4()
    else: promotion.benchmark_comparison.winner_result_id = uuid4(); promotion.override_winner = False
    promotions.get_with_details.return_value = promotion; original = dict(promotion.__dict__)
    with pytest.raises(error): await ModelPromotionService(promotions, comparisons).approve_promotion(ModelPromotionReviewInput(promotion.id, uuid4(), "note"))
    assert promotion.__dict__ == original; promotions.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_requester_can_cancel_and_other_user_cannot() -> None:
    promotions, comparisons = repositories(); promotion = decision(); promotions.get_with_details.side_effect = [promotion, promotion]
    returned = await ModelPromotionService(promotions, comparisons).cancel_promotion(ModelPromotionCancelInput(promotion.id, promotion.requested_by_user_id, "  withdrawn  "))
    assert returned.status is ModelPromotionStatus.CANCELLED
    assert returned.reviewed_by_user_id == promotion.requested_by_user_id and returned.review_note == "withdrawn"
    promotions, comparisons = repositories(); promotion = decision(); promotions.get_with_details.return_value = promotion
    with pytest.raises(InvalidModelPromotionError): await ModelPromotionService(promotions, comparisons).cancel_promotion(ModelPromotionCancelInput(promotion.id, uuid4(), "note"))
    promotions.flush.assert_not_awaited()


@pytest.mark.anyio
async def test_blank_review_and_cancel_notes_are_rejected_before_reads() -> None:
    promotions, comparisons = repositories(); service = ModelPromotionService(promotions, comparisons)
    with pytest.raises(InvalidModelPromotionError): await service.reject_promotion(ModelPromotionReviewInput(uuid4(), uuid4(), " "))
    with pytest.raises(InvalidModelPromotionError): await service.cancel_promotion(ModelPromotionCancelInput(uuid4(), uuid4(), " "))
    promotions.get_with_details.assert_not_awaited()


@pytest.mark.anyio
async def test_reads_delegate_and_translate_missing_without_writes() -> None:
    promotions, comparisons = repositories(); service = ModelPromotionService(promotions, comparisons); promotion = decision()
    promotions.get_with_details.return_value = promotion
    assert await service.get_promotion(promotion.id) is promotion
    assert await service.list_promotions(status=ModelPromotionStatus.PENDING, offset=3, limit=7) == []
    promotions.list_promotions.assert_awaited_once_with(status=ModelPromotionStatus.PENDING, offset=3, limit=7)
    promotions.get_with_details.return_value = None
    with pytest.raises(ModelPromotionNotFoundError): await service.get_promotion(uuid4())
    no_writes(promotions)
