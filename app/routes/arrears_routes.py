from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from ..models import Arrears, Customer, Loan, LoanStatus
from ..auth import get_current_user

router = APIRouter(prefix="/arrears", tags=["arrears"])


@router.get("/")
async def list_arrears(
    only_active: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    q = select(Arrears).order_by(Arrears.created_at.desc())
    if only_active:
        q = q.filter(Arrears.is_cleared == False)
    q = q.limit(limit).offset(offset)
    res = await db.execute(q)
    arrears_list = res.scalars().all()
    return [
        {
            "id": a.id,
            "customer_id": a.customer_id,
            "loan_id": a.loan_id,
            "original_amount": a.original_amount,
            "remaining_amount": a.remaining_amount,
            "arrears_date": a.arrears_date,
            "is_cleared": a.is_cleared,
            "created_at": a.created_at,
        } for a in arrears_list
    ]


@router.get("/{arrears_id}")
async def get_arrears(arrears_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    res = await db.execute(select(Arrears).filter(Arrears.id == arrears_id))
    arrears = res.scalar_one_or_none()
    if not arrears:
        raise HTTPException(status_code=404, detail="Arrears not found")
    return {
        "id": arrears.id,
        "customer_id": arrears.customer_id,
        "loan_id": arrears.loan_id,
        "original_amount": arrears.original_amount,
        "remaining_amount": arrears.remaining_amount,
        "arrears_date": arrears.arrears_date,
        "is_cleared": arrears.is_cleared,
        "created_at": arrears.created_at,
    }


class ArrearsPayment(BaseModel):
    amount: float


@router.post("/{arrears_id}/installments")
async def pay_arrears(arrears_id: int, body: ArrearsPayment,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    res = await db.execute(select(Arrears).filter(Arrears.id == arrears_id))
    arrears = res.scalar_one_or_none()
    if not arrears:
        raise HTTPException(status_code=404, detail="Arrears not found")
    if arrears.is_cleared:
        raise HTTPException(status_code=400, detail="Arrears already cleared")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    arrears.remaining_amount = max(0.0, float(arrears.remaining_amount) - float(body.amount))

    # Sync loan remaining amount and status
    loan_res = await db.execute(select(Loan).filter(Loan.id == arrears.loan_id))
    loan = loan_res.scalar_one_or_none()
    if loan:
        loan.remaining_amount = arrears.remaining_amount
        if arrears.remaining_amount == 0:
            arrears.is_cleared = True
            arrears.cleared_date = datetime.utcnow()
            loan.status = LoanStatus.COMPLETED
            loan.completed_at = datetime.utcnow()
        else:
            # Still owing; arrears loans remain ARREARS
            loan.status = LoanStatus.ARREARS
        db.add(loan)

    db.add(arrears)
    await db.commit()
    await db.refresh(arrears)
    return {"message": "Arrears payment recorded", "remaining_amount": arrears.remaining_amount, "is_cleared": arrears.is_cleared}


@router.post("/{arrears_id}/clear")
async def clear_arrears(arrears_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    res = await db.execute(select(Arrears).filter(Arrears.id == arrears_id))
    arrears = res.scalar_one_or_none()
    if not arrears:
        raise HTTPException(status_code=404, detail="Arrears not found")
    arrears.remaining_amount = 0.0
    arrears.is_cleared = True
    arrears.cleared_date = datetime.utcnow()
    db.add(arrears)
    # also complete linked loan and zero remaining
    loan_res = await db.execute(select(Loan).filter(Loan.id == arrears.loan_id))
    loan = loan_res.scalar_one_or_none()
    if loan and loan.status != LoanStatus.COMPLETED:
        loan.remaining_amount = 0.0
        loan.status = LoanStatus.COMPLETED
        loan.completed_at = datetime.utcnow()
        db.add(loan)
    await db.commit()
    await db.refresh(arrears)
    return {"message": "Arrears cleared"}




