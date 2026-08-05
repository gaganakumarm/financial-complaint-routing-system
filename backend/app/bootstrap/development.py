"""Idempotent canonical data bootstrap for local development."""

import asyncio
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.mixins import utc_now
from app.db.session import get_session_factory
from app.models import (
    ComplaintCategory,
    Department,
    ModelType,
    ModelVersion,
    Role,
)


class DevelopmentBootstrapError(Exception):
    """Raised when canonical development data cannot be installed safely."""


@dataclass(frozen=True, slots=True)
class DevelopmentBootstrapResult:
    customer_role_id: UUID
    reviewer_role_id: UUID
    administrator_role_id: UUID
    unauthorized_transaction_category_id: UUID
    general_enquiry_category_id: UUID
    fraud_investigation_department_id: UUID
    customer_support_department_id: UUID
    configured_model_version_id: UUID


async def _find(session: AsyncSession, model, field, value):
    result = await session.execute(select(model).where(field == value))
    return result.scalar_one_or_none()


async def _ensure_role(
    session: AsyncSession, *, name: str, display_name: str
) -> Role:
    role = await _find(session, Role, Role.name, name)
    if role is None:
        role = Role(
            name=name,
            display_name=display_name,
            description=f"Development {display_name.lower()} role.",
            is_active=True,
        )
        session.add(role)
        await session.flush()
    else:
        role.display_name = display_name
        role.is_active = True
    return role


async def _ensure_category(
    session: AsyncSession,
    *,
    code: str,
    display_name: str,
    description: str,
    is_high_risk: bool,
) -> ComplaintCategory:
    category = await _find(session, ComplaintCategory, ComplaintCategory.code, code)
    if category is None:
        category = ComplaintCategory(code=code)
        session.add(category)
    category.display_name = display_name
    category.description = description
    category.is_high_risk = is_high_risk
    category.is_active = True
    await session.flush()
    return category


async def _ensure_department(
    session: AsyncSession, *, code: str, display_name: str, description: str
) -> Department:
    department = await _find(session, Department, Department.code, code)
    if department is None:
        department = Department(code=code)
        session.add(department)
    department.display_name = display_name
    department.description = description
    department.is_active = True
    await session.flush()
    return department


async def bootstrap_development_data(
    session: AsyncSession,
) -> DevelopmentBootstrapResult:
    """Create or reconcile canonical records without owning the transaction."""
    customer = await _ensure_role(session, name="customer", display_name="Customer")
    reviewer = await _ensure_role(session, name="reviewer", display_name="Reviewer")
    administrator = await _ensure_role(
        session, name="administrator", display_name="Administrator"
    )
    unauthorized = await _ensure_category(
        session,
        code="unauthorized_transaction",
        display_name="Unauthorized Transaction",
        description="Complaints involving transactions not authorized by the customer.",
        is_high_risk=True,
    )
    general = await _ensure_category(
        session,
        code="general_enquiry",
        display_name="General Enquiry",
        description="General financial-service questions and uncategorized complaints.",
        is_high_risk=False,
    )
    fraud = await _ensure_department(
        session,
        code="fraud_investigation",
        display_name="Fraud Investigation",
        description="Handles suspected unauthorized and fraudulent transactions.",
    )
    support = await _ensure_department(
        session,
        code="customer_support",
        display_name="Customer Support",
        description="Handles general customer complaints and service enquiries.",
    )

    model_result = await session.execute(
        select(ModelVersion).where(
            ModelVersion.name == "Configured Baseline",
            ModelVersion.version == "development-v1",
        )
    )
    model = model_result.scalar_one_or_none()
    active_result = await session.execute(
        select(ModelVersion).where(ModelVersion.is_active.is_(True))
    )
    active = active_result.scalar_one_or_none()
    if active is not None and active is not model:
        raise DevelopmentBootstrapError(
            "Another active model version already exists."
        )
    if model is None:
        model = ModelVersion(name="Configured Baseline", version="development-v1")
        session.add(model)
    model.model_type = ModelType.TFIDF_CLASSIFIER
    model.base_model_name = None
    model.artifact_location = None
    model.is_approved = True
    model.is_active = True
    model.activated_at = model.activated_at or utc_now()
    model.deactivated_at = None
    model.configuration = {
        "default_category_id": str(general.id),
        "default_department_id": str(support.id),
        "default_urgency": "medium",
        "default_confidence_score": 0.70,
        "keyword_rules": [
            {
                "keywords": [
                    "unauthorized",
                    "fraud",
                    "not authorize",
                    "not authorised",
                    "unknown transaction",
                ],
                "category_id": str(unauthorized.id),
                "department_id": str(fraud.id),
                "urgency": "high",
                "confidence_score": 0.82,
            }
        ],
    }
    await session.flush()

    return DevelopmentBootstrapResult(
        customer_role_id=customer.id,
        reviewer_role_id=reviewer.id,
        administrator_role_id=administrator.id,
        unauthorized_transaction_category_id=unauthorized.id,
        general_enquiry_category_id=general.id,
        fraud_investigation_department_id=fraud.id,
        customer_support_department_id=support.id,
        configured_model_version_id=model.id,
    )


async def _run_cli() -> None:
    async with get_session_factory()() as session:
        async with session.begin():
            result = await bootstrap_development_data(session)
    print("Development bootstrap completed.")
    print(f"customer_role_id: {result.customer_role_id}")
    print(f"reviewer_role_id: {result.reviewer_role_id}")
    print(f"administrator_role_id: {result.administrator_role_id}")
    print(f"configured_model_version_id: {result.configured_model_version_id}")


def _main() -> None:
    asyncio.run(_run_cli())


if __name__ == "__main__":
    _main()
