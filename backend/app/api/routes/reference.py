"""Role-protected controlled reference-data routes."""

from fastapi import APIRouter

from app.api.dependencies import (
    ComplaintCategoryRepositoryDependency,
    DepartmentRepositoryDependency,
)
from app.authz import ReviewerOrAdministratorUser
from app.schemas.reference import (
    ComplaintCategoryReferenceItem,
    ComplaintCategoryReferenceList,
    DepartmentReferenceItem,
    DepartmentReferenceList,
)


router = APIRouter(prefix="/reference", tags=["Reference Data"])


@router.get(
    "/complaint-categories",
    response_model=ComplaintCategoryReferenceList,
)
async def list_complaint_categories(
    current_user: ReviewerOrAdministratorUser,
    repository: ComplaintCategoryRepositoryDependency,
) -> ComplaintCategoryReferenceList:
    del current_user
    categories = await repository.list_active()
    return ComplaintCategoryReferenceList(
        items=[ComplaintCategoryReferenceItem.model_validate(item) for item in categories],
        count=len(categories),
    )


@router.get("/departments", response_model=DepartmentReferenceList)
async def list_departments(
    current_user: ReviewerOrAdministratorUser,
    repository: DepartmentRepositoryDependency,
) -> DepartmentReferenceList:
    del current_user
    departments = await repository.list_active()
    return DepartmentReferenceList(
        items=[DepartmentReferenceItem.model_validate(item) for item in departments],
        count=len(departments),
    )
