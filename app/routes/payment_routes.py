from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_
from datetime import datetime
from pydantic import BaseModel
from typing import Optional
from ..database import get_db
from ..models import Loan, Customer, Installment, LoanStatus, Arrears
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
    
    # Find ACTIVE loan only (overdue/arrears loans must be paid through arrears page)
    loan_result = await db.execute(
        select(Loan).filter(
            and_(
                Loan.customer_id == payment.id_number,
                Loan.status == LoanStatus.ACTIVE
            )
        ).order_by(Loan.id.desc())
    )
    loan = loan_result.scalar_one_or_none()
    
    if not loan:
        # Check if they have overdue/arrears loans
        overdue_check = await db.execute(
            select(Loan).filter(
                and_(
                    Loan.customer_id == payment.id_number,
                    Loan.status.in_([LoanStatus.OVERDUE, LoanStatus.ARREARS])
                )
            )
        )
        has_overdue = overdue_check.scalar_one_or_none() is not None
        
        if has_overdue:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This loan is overdue or in arrears. Please pay through the Arrears page."
            )
        
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
    
    # Update remaining amount on the loan
    current_remaining = loan.remaining_amount if loan.remaining_amount is not None else loan.total_amount
    new_remaining = max(0.0, current_remaining - payment.amount)
    loan.remaining_amount = new_remaining

    # Determine if fully paid
    if new_remaining <= 0:
        loan.status = LoanStatus.COMPLETED
        loan.completed_at = datetime.utcnow()
    else:
        # If due date is past, mark as overdue and create/update arrears record
        if loan.due_date and loan.due_date < datetime.utcnow().date():
            # Mark status as ARREARS
            loan.status = LoanStatus.ARREARS

            # Find or create arrears for this loan
            arrears_result = await db.execute(
                select(Arrears).filter(Arrears.loan_id == loan.id)
            )
            arrears = arrears_result.scalar_one_or_none()

            if not arrears:
                # Need customer's internal id for Arrears.customer_id
                customer_result2 = await db.execute(
                    select(Customer).filter(Customer.id_number == loan.customer_id)
                )
                customer2 = customer_result2.scalar_one_or_none()
                customer_int_id = customer2.id if customer2 else None

                arrears = Arrears(
                    loan_id=loan.id,
                    customer_id=customer_int_id,
                    original_amount=loan.total_amount,
                    remaining_amount=new_remaining,
                    is_cleared=False,
                )
                db.add(arrears)
            else:
                arrears.remaining_amount = new_remaining
    
    await db.commit()
    await db.refresh(installment)
    await db.refresh(loan)
    
    return {
        "message": "Payment recorded successfully",
        "installment_id": installment.id,
        "remaining_balance": loan.remaining_amount,
        "loan_status": loan.status.value,
    }

