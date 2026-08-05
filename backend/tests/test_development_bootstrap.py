"""Tests for development bootstrap behavior without PostgreSQL."""

from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.bootstrap import bootstrap_development_data
from app.models import ComplaintCategory, Department, ModelVersion, Role


class Result:
    def __init__(self, value): self.value = value
    def scalar_one_or_none(self): return self.value


class FakeSession:
    def __init__(self):
        self.records = []
        self.commit = MagicMock()
        self.rollback = MagicMock()
        self.begin = MagicMock()

    def add(self, value): self.records.append(value)

    async def flush(self):
        for value in self.records:
            if "id" not in value.__dict__: value.id = uuid4()

    async def execute(self, statement):
        model = statement.column_descriptions[0]["entity"]
        params = set(statement.compile().params.values())
        candidates = [item for item in self.records if isinstance(item, model)]
        if model is Role:
            value = next((x for x in candidates if x.name in params), None)
        elif model in (ComplaintCategory, Department):
            value = next((x for x in candidates if x.code in params), None)
        elif "Configured Baseline" in params:
            value = next((x for x in candidates if x.name == "Configured Baseline" and x.version == "development-v1"), None)
        else:
            value = next((x for x in candidates if x.is_active), None)
        return Result(value)


@pytest.mark.anyio
async def test_bootstrap_is_canonical_idempotent_and_transaction_neutral() -> None:
    session = FakeSession()
    first = await bootstrap_development_data(session)
    second = await bootstrap_development_data(session)
    assert first == second
    assert len([x for x in session.records if isinstance(x, Role)]) == 3
    categories = {x.code: x for x in session.records if isinstance(x, ComplaintCategory)}
    departments = {x.code: x for x in session.records if isinstance(x, Department)}
    assert categories["unauthorized_transaction"].display_name == "Unauthorized Transaction"
    assert categories["general_enquiry"].display_name == "General Enquiry"
    assert departments["fraud_investigation"].display_name == "Fraud Investigation"
    assert departments["customer_support"].display_name == "Customer Support"
    model = next(x for x in session.records if isinstance(x, ModelVersion))
    assert model.artifact_location is None
    assert model.activated_at is not None and model.is_active and model.is_approved
    assert model.configuration["default_category_id"] == str(first.general_enquiry_category_id)
    assert model.configuration["keyword_rules"][0]["department_id"] == str(first.fraud_investigation_department_id)
    session.commit.assert_not_called()
    session.rollback.assert_not_called()
    session.begin.assert_not_called()
