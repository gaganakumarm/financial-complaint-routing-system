"""PostgreSQL end-to-end tests for the deployment-governance workflow."""

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.core.config import Settings
from app.db.base import Base
from app.db.session import get_db_session, get_transactional_session
from app.main import create_app
from app.models import (
    BenchmarkComparison,
    BenchmarkExperiment,
    BenchmarkExperimentStatus,
    BenchmarkResult,
    DatasetSplit,
    DatasetVersion,
    DeploymentCandidate,
    DeploymentCandidateStatus,
    DeploymentCandidateStatusHistory,
    ModelPromotionDecision,
    ModelPromotionStatus,
    ModelType,
    ModelVersion,
    Role,
    User,
)
from app.security import create_access_token


TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = [
    pytest.mark.anyio,
    pytest.mark.skipif(
        not TEST_DATABASE_URL,
        reason="Set TEST_DATABASE_URL to a disposable PostgreSQL database for governance integration tests.",
    ),
]


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(str(user.id))}"}


def _result(experiment: BenchmarkExperiment, model: ModelVersion, *, error: str, accuracy: str, latency: int) -> BenchmarkResult:
    return BenchmarkResult(
        experiment=experiment,
        model_version=model,
        sample_count=25,
        total_error_cost=Decimal(error),
        exact_match_accuracy=Decimal(accuracy),
        failed_prediction_count=0,
        department_accuracy=Decimal(accuracy),
        category_accuracy=Decimal(accuracy),
        urgency_accuracy=Decimal(accuracy),
        p95_inference_latency_ms=latency,
        average_inference_latency_ms=Decimal(latency) / 2,
        cost_weighted_error=Decimal(error),
    )


async def _request_promotion(client, reviewer, comparison, result):
    response = await client.post(
        "/api/model-promotions",
        headers=_headers(reviewer),
        json={
            "benchmark_comparison_id": comparison["id"],
            "selected_benchmark_result_id": result["id"],
            "rationale": "Deterministic benchmark winner",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _approve_and_create_candidate(client, administrator, promotion):
    approved = await client.post(
        f"/api/model-promotions/{promotion['id']}/approve",
        headers=_headers(administrator),
        json={"review_note": "Approved for controlled deployment"},
    )
    assert approved.status_code == 200, approved.text
    created = await client.post(
        "/api/deployment-candidates",
        headers=_headers(administrator),
        json={"model_promotion_decision_id": promotion["id"], "notes": "Registered from approved promotion"},
    )
    assert created.status_code == 201, created.text
    return approved.json(), created.json()


async def test_complete_deployment_governance_and_active_replacement() -> None:
    assert TEST_DATABASE_URL is not None
    if not TEST_DATABASE_URL.startswith("postgresql+asyncpg://"):
        pytest.skip("TEST_DATABASE_URL must use postgresql+asyncpg.")

    engine = create_async_engine(TEST_DATABASE_URL)
    connection = await engine.connect()
    transaction = await connection.begin()
    session = AsyncSession(bind=connection, autoflush=False, expire_on_commit=False)
    try:
        await connection.run_sync(Base.metadata.create_all)
        suffix = uuid4().hex
        administrator_role = Role(name=f"administrator-{suffix}", display_name="Administrator", is_active=True)
        reviewer_role = Role(name=f"reviewer-{suffix}", display_name="Reviewer", is_active=True)
        customer_role = Role(name=f"customer-{suffix}", display_name="Customer", is_active=True)
        # Authorization uses canonical role names, so isolate rows through the disposable database requirement.
        administrator_role.name, reviewer_role.name, customer_role.name = "administrator", "reviewer", "customer"
        administrator = User(role=administrator_role, email=f"admin-{suffix}@example.com", password_hash="integration-only", full_name="Administrator", is_active=True, email_verified=True)
        reviewer = User(role=reviewer_role, email=f"reviewer-{suffix}@example.com", password_hash="integration-only", full_name="Reviewer", is_active=True, email_verified=True)
        customer = User(role=customer_role, email=f"customer-{suffix}@example.com", password_hash="integration-only", full_name="Customer", is_active=True, email_verified=True)
        dataset = DatasetVersion(name=f"governance-{suffix}", version="v1", source_name="integration", taxonomy_version="v1", split=DatasetSplit.FULL, record_count=25, content_hash=suffix, preparation_details={})
        first_model = ModelVersion(name=f"router-{suffix}", version="v1", model_type=ModelType.TFIDF_CLASSIFIER, configuration={}, is_approved=True)
        second_model = ModelVersion(name=f"router-{suffix}", version="v2", model_type=ModelType.TFIDF_CLASSIFIER, configuration={}, is_approved=True)
        now = datetime.now(timezone.utc)
        experiment = BenchmarkExperiment(name=f"completed-{suffix}", dataset_version=dataset, status=BenchmarkExperimentStatus.COMPLETED, configuration={}, started_at=now, completed_at=now)
        winner = _result(experiment, first_model, error="1.0", accuracy="0.96", latency=20)
        runner_up = _result(experiment, second_model, error="3.0", accuracy="0.90", latency=35)
        session.add_all([administrator, reviewer, customer, winner, runner_up])
        await session.flush()

        async def shared_session():
            yield session

        application = create_app(Settings())
        application.dependency_overrides[get_db_session] = shared_session
        application.dependency_overrides[get_transactional_session] = shared_session
        transport = httpx.ASGITransport(app=application)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthenticated = await client.get("/api/deployment-candidates")
            forbidden = await client.get("/api/deployment-candidates", headers=_headers(customer))
            assert (unauthenticated.status_code, forbidden.status_code) == (401, 403)

            comparison_response = await client.post(
                "/api/benchmark-comparisons",
                headers=_headers(reviewer),
                json={"benchmark_result_ids": [str(runner_up.id), str(winner.id)], "ranking_metric": "deterministic-v1"},
            )
            assert comparison_response.status_code == 201, comparison_response.text
            comparison = comparison_response.json()
            assert comparison["winner_result_id"] == str(winner.id)
            assert [member["rank"] for member in comparison["members"]] == [1, 2]
            assert [member["benchmark_result_id"] for member in comparison["members"]] == [str(winner.id), str(runner_up.id)]
            assert await session.get(BenchmarkComparison, comparison["id"]) is not None

            promotion = await _request_promotion(client, reviewer, comparison, {"id": str(winner.id)})
            assert promotion["status"] == "pending"
            assert promotion["selected_model_version_id"] == str(first_model.id)
            assert promotion["requested_by_user_id"] == str(reviewer.id)
            approved, candidate = await _approve_and_create_candidate(client, administrator, promotion)
            assert approved["status"] == "approved" and approved["reviewed_by_user_id"] == str(administrator.id)
            assert approved["review_note"] == "Approved for controlled deployment"
            assert candidate["status"] == "candidate"
            assert candidate["benchmark_result_id"] == str(winner.id)
            assert candidate["model_version_id"] == str(first_model.id)
            assert candidate["registered_by_user_id"] == str(administrator.id)

            staged = await client.post(f"/api/deployment-candidates/{candidate['id']}/stage", headers=_headers(administrator), json={"note": "Staged"})
            assert staged.status_code == 200 and staged.json()["status"] == "staged" and staged.json()["staged_at"]
            activated = await client.post(f"/api/deployment-candidates/{candidate['id']}/activate", headers=_headers(administrator), json={"note": "Activated"})
            assert activated.status_code == 200 and activated.json()["status"] == "active" and activated.json()["activated_at"]
            active = await client.get("/api/deployment-candidates/active", headers=_headers(reviewer))
            assert active.status_code == 200 and active.json()["id"] == candidate["id"]
            history = await client.get(f"/api/deployment-candidates/{candidate['id']}/history", headers=_headers(reviewer))
            assert history.status_code == 200
            assert [(row["previous_status"], row["new_status"]) for row in history.json()["items"]] == [(None, "candidate"), ("candidate", "staged"), ("staged", "active")]

            second_comparison_response = await client.post(
                "/api/benchmark-comparisons",
                headers=_headers(administrator),
                json={"benchmark_result_ids": [str(winner.id), str(runner_up.id)], "ranking_metric": "deterministic-v1"},
            )
            assert second_comparison_response.status_code == 201, second_comparison_response.text
            second_promotion = await _request_promotion(client, reviewer, second_comparison_response.json(), {"id": str(winner.id)})
            _, second_candidate = await _approve_and_create_candidate(client, administrator, second_promotion)
            assert (await client.post(f"/api/deployment-candidates/{second_candidate['id']}/stage", headers=_headers(administrator), json={})).status_code == 200
            second_activation = await client.post(f"/api/deployment-candidates/{second_candidate['id']}/activate", headers=_headers(administrator), json={})
            assert second_activation.status_code == 200 and second_activation.json()["status"] == "active"
            current_active = await client.get("/api/deployment-candidates/active", headers=_headers(reviewer))
            assert current_active.status_code == 200 and current_active.json()["id"] == second_candidate["id"]
            second_history = await client.get(f"/api/deployment-candidates/{second_candidate['id']}/history", headers=_headers(reviewer))
            assert [(row["previous_status"], row["new_status"]) for row in second_history.json()["items"]] == [(None, "candidate"), ("candidate", "staged"), ("staged", "active")]

            retired = await client.get(f"/api/deployment-candidates/{candidate['id']}", headers=_headers(reviewer))
            assert retired.status_code == 200 and retired.json()["status"] == "retired"
            retired_history = await client.get(f"/api/deployment-candidates/{candidate['id']}/history", headers=_headers(reviewer))
            assert [(row["previous_status"], row["new_status"]) for row in retired_history.json()["items"]] == [(None, "candidate"), ("candidate", "staged"), ("staged", "active"), ("active", "retired")]
            assert retired_history.json()["items"][-1]["note"] == "Replaced by another active deployment candidate."
            assert retired_history.json()["items"][-1]["changed_by_user_id"] == str(administrator.id)

        persisted_promotion = await session.get(ModelPromotionDecision, promotion["id"])
        persisted_candidate = await session.get(DeploymentCandidate, candidate["id"])
        persisted_history = list((await session.execute(select(DeploymentCandidateStatusHistory).where(DeploymentCandidateStatusHistory.deployment_candidate_id == persisted_candidate.id).order_by(DeploymentCandidateStatusHistory.changed_at, DeploymentCandidateStatusHistory.id))).scalars())
        assert persisted_promotion.status is ModelPromotionStatus.APPROVED
        assert persisted_candidate.status is DeploymentCandidateStatus.RETIRED
        assert len(persisted_history) == 4
        assert transaction.is_active
    finally:
        await session.close()
        if transaction.is_active:
            await transaction.rollback()
        await connection.close()
        await engine.dispose()
