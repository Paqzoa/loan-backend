from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from ..models import Alias, Customer, Loan, LoanStatus
from ..auth import get_current_user

router = APIRouter(prefix="/aliases", tags=["aliases"])


@router.get("/")
async def list_aliases(
    only_active: bool = True,
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    q = select(Alias).order_by(Alias.created_at.desc())
    if only_active:
        q = q.filter(Alias.is_cleared == False)
    q = q.limit(limit).offset(offset)
    res = await db.execute(q)
    aliases = res.scalars().all()
    return [
        {
            "id": a.id,
            "customer_id": a.customer_id,
            "loan_id": a.loan_id,
            "original_amount": a.original_amount,
            "remaining_amount": a.remaining_amount,
            "alias_date": a.alias_date,
            "is_cleared": a.is_cleared,
            "created_at": a.created_at,
        } for a in aliases
    ]


@router.get("/{alias_id}")
async def get_alias(alias_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    res = await db.execute(select(Alias).filter(Alias.id == alias_id))
    alias = res.scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")
    return {
        "id": alias.id,
        "customer_id": alias.customer_id,
        "loan_id": alias.loan_id,
        "original_amount": alias.original_amount,
        "remaining_amount": alias.remaining_amount,
        "alias_date": alias.alias_date,
        "is_cleared": alias.is_cleared,
        "created_at": alias.created_at,
    }


class AliasPayment(BaseModel):
    amount: float


@router.post("/{alias_id}/installments")
async def pay_alias(alias_id: int, body: AliasPayment,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    res = await db.execute(select(Alias).filter(Alias.id == alias_id))
    alias = res.scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")
    if alias.is_cleared:
        raise HTTPException(status_code=400, detail="Alias already cleared")
    if body.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")

    alias.remaining_amount = max(0.0, float(alias.remaining_amount) - float(body.amount))
    if alias.remaining_amount == 0:
        alias.is_cleared = True
        alias.cleared_date = datetime.utcnow()
        # also complete linked loan
        loan_res = await db.execute(select(Loan).filter(Loan.id == alias.loan_id))
        loan = loan_res.scalar_one_or_none()
        if loan and loan.status != LoanStatus.COMPLETED:
            loan.status = LoanStatus.COMPLETED
            loan.completed_at = datetime.utcnow()
            db.add(loan)
    db.add(alias)
    await db.commit()
    await db.refresh(alias)
    return {"message": "Alias payment recorded", "remaining_amount": alias.remaining_amount, "is_cleared": alias.is_cleared}


@router.post("/{alias_id}/clear")
async def clear_alias(alias_id: int,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    res = await db.execute(select(Alias).filter(Alias.id == alias_id))
    alias = res.scalar_one_or_none()
    if not alias:
        raise HTTPException(status_code=404, detail="Alias not found")
    alias.remaining_amount = 0.0
    alias.is_cleared = True
    alias.cleared_date = datetime.utcnow()
    db.add(alias)
    # also complete linked loan
    loan_res = await db.execute(select(Loan).filter(Loan.id == alias.loan_id))
    loan = loan_res.scalar_one_or_none()
    if loan and loan.status != LoanStatus.COMPLETED:
        loan.status = LoanStatus.COMPLETED
        loan.completed_at = datetime.utcnow()
        db.add(loan)
    await db.commit()
    await db.refresh(alias)
    return {"message": "Alias cleared"}


