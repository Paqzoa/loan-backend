import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from ..database import get_db
from ..models import Loan, Customer, LoanStatus, Arrears, Guarantor
from ..schemas import LoanCreate, LoanResponse, LoanUpdate, GuarantorUpdate
from ..auth import get_current_user
from ..services.loan_pdf_service import generate_loan_receipt

router = APIRouter(prefix="/loans", tags=["loans"])
logger = logging.getLogger(__name__)

@router.post("/", response_model=LoanResponse)
async def create_loan(loan: LoanCreate, db: AsyncSession = Depends(get_db), current_user = Depends(get_current_user)):
    """Create a new loan"""
    # Check if customer exists by id_number
    result = await db.execute(select(Customer).filter(Customer.id_number == loan.id_number))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Check for active loans
    loan_result = await db.execute(
        select(Loan).filter(
            Loan.customer_id == loan.id_number,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE])
        )
    )
    active_loan = loan_result.scalar_one_or_none()
    
    if active_loan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer already has an active loan"
        )
    
    # Check for active arrears
    arrears_result = await db.execute(
        select(Arrears).filter(
            Arrears.customer_id == customer.id,
            Arrears.is_cleared == False
        )
    )
    active_arrears = arrears_result.scalar_one_or_none()
    
    if active_arrears:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer has active arrears that must be cleared first"
        )
    
    # Create guarantor if provided
    guarantor_id = None
    if loan.guarantor:
        db_guarantor = Guarantor(
            name=loan.guarantor.name,
            id_number=loan.guarantor.id_number,
            phone=loan.guarantor.phone,
            location=loan.guarantor.location,
            relationship=loan.guarantor.relationship
        )
        db.add(db_guarantor)
        await db.flush()  # Flush to get the guarantor ID
        guarantor_id = db_guarantor.id
    
    # Create new loan
    db_loan = Loan(
        customer_id=loan.id_number,
        guarantor_id=guarantor_id,
        amount=loan.amount,
        interest_rate=20.0,
        start_date=loan.start_date
    )
    
    db.add(db_loan)
    await db.commit()
    await db.refresh(db_loan)
    
    # Load relationships
    await db.refresh(db_loan, ["guarantor"])

    # Generate receipt but don't block loan creation if it fails
    document_url = f"/loans/{db_loan.id}/printable"
    try:
        generate_loan_receipt(db_loan, customer=customer, guarantor=db_loan.guarantor)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Failed to generate loan receipt for loan %s: %s", db_loan.id, exc)
    
    setattr(db_loan, "document_url", document_url)
    return db_loan


@router.patch("/{loan_id}", response_model=LoanResponse)
async def update_loan(
    loan_id: int,
    payload: LoanUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update loan details (amount, interest, dates) and recompute totals, preserving amounts already paid."""
    result = await db.execute(
        select(Loan).filter(Loan.id == loan_id).options(selectinload(Loan.guarantor), selectinload(Loan.customer))
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan not found")

    # Optional guard: prevent edits on completed loans
    if loan.status == LoanStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit a completed loan")

    # Calculate already-paid amount before changes
    already_paid = max(0.0, float(loan.total_amount or 0) - float(loan.remaining_amount or 0))

    # Update amount if provided
    if payload.amount is not None:
        loan.amount = float(payload.amount)

    # Update interest rate if provided
    if payload.interest_rate is not None:
        loan.interest_rate = float(payload.interest_rate)

    # Recalculate total_amount based on current amount and interest_rate
    new_interest_rate = loan.interest_rate or 20.0
    new_total = float(loan.amount) + float(loan.amount) * (new_interest_rate / 100.0)
    loan.total_amount = new_total
    loan.remaining_amount = max(0.0, new_total - already_paid)

    # Update dates if provided
    if payload.start_date is not None:
        loan.start_date = payload.start_date
        # If due_date not explicitly provided, recalculate it (30 days from start_date)
        if payload.due_date is None:
            loan.due_date = payload.start_date + timedelta(days=30)
    
    if payload.due_date is not None:
        loan.due_date = payload.due_date

    # Persist
    await db.commit()
    await db.refresh(loan)
    await db.refresh(loan, ["guarantor", "customer"])

    document_url = f"/loans/{loan.id}/printable"
    setattr(loan, "document_url", document_url)
    return loan


@router.get("/active")
async def list_active_loans(
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """List active loans (ACTIVE and OVERDUE) with optional search by loan id or customer id_number."""
    stmt = (
        select(Loan)
        .options(selectinload(Loan.guarantor), selectinload(Loan.customer))
        .filter(Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]))
        .order_by(Loan.created_at.desc())
        .limit(limit).offset(offset)
    )
    if q:
        if q.isdigit():
            stmt = stmt.filter(Loan.id == int(q))
        else:
            stmt = stmt.filter(Loan.customer_id.ilike(f"%{q}%"))
    result = await db.execute(stmt)
    loans = result.scalars().all()
    return [
        {
            "id": l.id,
            "amount": l.amount,
            "interest_rate": l.interest_rate,
            "total_amount": l.total_amount,
            "remaining_amount": l.remaining_amount,
            "start_date": l.start_date,
            "due_date": l.due_date,
            "status": l.status.value,
            "customer": {
                "name": l.customer.name if l.customer else None,
                "id_number": l.customer_id,
                "phone": l.customer.phone if l.customer else None,
                "location": l.customer.location if l.customer else None,
                "profile_image_url": l.customer.profile_image_url if l.customer else None,
            },
            "guarantor": ({
                "id": l.guarantor.id,
                "name": l.guarantor.name,
                "id_number": l.guarantor.id_number,
                "phone": l.guarantor.phone,
                "location": l.guarantor.location,
                "relationship": l.guarantor.relationship,
            } if l.guarantor else None),
        }
        for l in loans
    ]


@router.get("/{loan_id}")
async def get_loan_details(
    loan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Get detailed info for a specific loan including customer and guarantor."""
    result = await db.execute(
        select(Loan)
        .options(selectinload(Loan.customer), selectinload(Loan.guarantor))
        .filter(Loan.id == loan_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    return {
        "id": loan.id,
        "amount": loan.amount,
        "interest_rate": loan.interest_rate,
        "total_amount": loan.total_amount,
        "remaining_amount": loan.remaining_amount,
        "start_date": loan.start_date,
        "due_date": loan.due_date,
        "status": loan.status.value,
        "created_at": loan.created_at,
        "customer": {
            "name": loan.customer.name if loan.customer else None,
            "id_number": loan.customer_id,
            "phone": loan.customer.phone if loan.customer else None,
            "location": loan.customer.location if loan.customer else None,
            "profile_image_url": loan.customer.profile_image_url if loan.customer else None,
        },
        "guarantor": ({
            "id": loan.guarantor.id,
            "name": loan.guarantor.name,
            "id_number": loan.guarantor.id_number,
            "phone": loan.guarantor.phone,
            "location": loan.guarantor.location,
            "relationship": loan.guarantor.relationship,
        } if loan.guarantor else None),
    }


@router.get("/{loan_id}/printable", response_class=FileResponse)
async def download_loan_receipt(
    loan_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Generate or refresh the PDF summary for a specific loan."""
    result = await db.execute(
        select(Loan)
        .options(selectinload(Loan.customer), selectinload(Loan.guarantor))
        .filter(Loan.id == loan_id)
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")

    customer = loan.customer
    if not customer:
        cust_result = await db.execute(select(Customer).filter(Customer.id_number == loan.customer_id))
        customer = cust_result.scalar_one_or_none()

    if not customer:
        raise HTTPException(status_code=500, detail="Customer details missing for this loan")

    filepath, filename = generate_loan_receipt(loan, customer=customer, guarantor=loan.guarantor)
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=filename
    )


@router.patch("/{loan_id}/guarantor/{guarantor_id}", response_model=LoanResponse)
async def update_guarantor(
    loan_id: int,
    guarantor_id: int,
    payload: GuarantorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user),
):
    """Update guarantor details for a specific loan."""
    # Verify loan exists and belongs to this guarantor
    result = await db.execute(
        select(Loan).filter(Loan.id == loan_id, Loan.guarantor_id == guarantor_id)
        .options(selectinload(Loan.guarantor), selectinload(Loan.customer))
    )
    loan = result.scalar_one_or_none()
    if not loan:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loan or guarantor not found")

    if loan.status == LoanStatus.COMPLETED:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot edit guarantor for a completed loan")

    # Get guarantor
    guarantor_result = await db.execute(select(Guarantor).filter(Guarantor.id == guarantor_id))
    guarantor = guarantor_result.scalar_one_or_none()
    if not guarantor:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Guarantor not found")

    # Update guarantor fields
    if payload.name is not None:
        guarantor.name = payload.name
    if payload.id_number is not None:
        guarantor.id_number = payload.id_number
    if payload.phone is not None:
        guarantor.phone = payload.phone
    if payload.location is not None:
        guarantor.location = payload.location
    if payload.relationship is not None:
        guarantor.relationship = payload.relationship

    await db.commit()
    await db.refresh(loan)
    await db.refresh(loan, ["guarantor", "customer"])

    document_url = f"/loans/{loan.id}/printable"
    setattr(loan, "document_url", document_url)
    return loan