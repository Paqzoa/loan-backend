from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import List

from ..database import get_db
from ..models import Loan, Customer, LoanStatus, Alias
from ..schemas import LoanCreate, LoanResponse
from ..auth import get_current_user

router = APIRouter(prefix="/loans", tags=["loans"])

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
    
    # Check for active aliases
    alias_result = await db.execute(
        select(Alias).filter(
            Alias.customer_id == customer.id,
            Alias.is_cleared == False
        )
    )
    active_alias = alias_result.scalar_one_or_none()
    
    if active_alias:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Customer has an active alias that must be cleared first"
        )
    
    # Create new loan
    db_loan = Loan(
        customer_id=loan.id_number,
        amount=loan.amount,
        interest_rate=loan.interest_rate,
        start_date=loan.start_date
    )
    
    db.add(db_loan)
    await db.commit()
    await db.refresh(db_loan)
    return db_loan