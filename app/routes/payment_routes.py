from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from ..models import Loan, Customer, Installment, LoanStatus
from ..auth import get_current_user

router = APIRouter(prefix="/payments", tags=["payments"])


class PaymentCreate(BaseModel):
    id_number: str
    amount: float


@router.post("/")
async def record_payment(
    payment: PaymentCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Record a payment/installment for a customer's loan"""
    
    # Find customer by ID number
    customer_result = await db.execute(
        select(Customer).filter(Customer.id_number == payment.id_number)
    )
    customer = customer_result.scalar_one_or_none()
    
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Find active loan for this customer
    loan_result = await db.execute(
        select(Loan).filter(
            and_(
                Loan.customer_id == payment.id_number,
                Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE])
            )
        ).order_by(Loan.id.desc())
    )
    loan = loan_result.scalar_one_or_none()
    
    if not loan:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active loan found for this customer"
        )
    
    # Create installment record
    installment = Installment(
        loan_id=loan.id,
        amount=payment.amount,
        payment_date=datetime.utcnow()
    )
    
    db.add(installment)
    
    # Check if loan is fully paid
    total_paid_result = await db.execute(
        select(func.sum(Installment.amount)).filter(
            Installment.loan_id == loan.id
        )
    )
    total_paid = total_paid_result.scalar() or 0
    
    if total_paid + payment.amount >= loan.total_amount:
        loan.status = LoanStatus.COMPLETED
        loan.completed_at = datetime.utcnow()
    
    await db.commit()
    await db.refresh(installment)
    
    return {
        "message": "Payment recorded successfully",
        "installment_id": installment.id,
        "remaining_balance": max(0, loan.total_amount - (total_paid + payment.amount))
    }

