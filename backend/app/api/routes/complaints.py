"""Customer-facing complaint API routes."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from app.api.dependencies import (
    ComplaintServiceDependency,
    TransactionalComplaintServiceDependency,
)
from app.authz import CustomerUser
from app.schemas import (
    ComplaintCreateRequest,
    ComplaintCreateResponse,
    ComplaintListResponse,
    ComplaintResponse,
)
from app.services import (
    ComplaintAccessDeniedError,
    ComplaintNotFoundError,
    InvalidComplaintDataError,
)


router = APIRouter(prefix="/complaints", tags=["Complaints"])


@router.post(
    "",
    response_model=ComplaintCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_complaint(
    payload: ComplaintCreateRequest,
    current_user: CustomerUser,
    complaint_service: TransactionalComplaintServiceDependency,
) -> ComplaintCreateResponse:
    try:
        complaint = await complaint_service.create_complaint(
            customer=current_user,
            title=payload.title,
            description=payload.description,
        )
    except InvalidComplaintDataError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Invalid complaint data",
        ) from None
    except ComplaintAccessDeniedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions",
        ) from None
    return ComplaintCreateResponse(
        complaint=ComplaintResponse.model_validate(complaint)
    )


@router.get("", response_model=ComplaintListResponse)
async def list_my_complaints(
    current_user: CustomerUser,
    complaint_service: ComplaintServiceDependency,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
) -> ComplaintListResponse:
    complaints = await complaint_service.list_customer_complaints(
        customer_id=current_user.id,
        offset=offset,
        limit=limit,
    )
    return ComplaintListResponse(
        items=[ComplaintResponse.model_validate(item) for item in complaints],
        offset=offset,
        limit=limit,
        count=len(complaints),
    )


@router.get("/{complaint_id}", response_model=ComplaintResponse)
async def get_my_complaint(
    complaint_id: UUID,
    current_user: CustomerUser,
    complaint_service: ComplaintServiceDependency,
) -> ComplaintResponse:
    try:
        complaint = await complaint_service.get_customer_complaint(
            complaint_id=complaint_id,
            customer_id=current_user.id,
        )
    except (ComplaintNotFoundError, ComplaintAccessDeniedError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Complaint not found",
        ) from None
    return ComplaintResponse.model_validate(complaint)
