from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, and_, or_
from datetime import datetime, date, timedelta
from typing import List
from ..database import get_db
from ..models import Loan, Customer, Alias, LoanStatus, Installment
from ..auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/metrics")
async def get_dashboard_metrics(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get dashboard metrics: active loans count and aliases count"""
    # Active loans (active + overdue)
    active_statuses = [LoanStatus.ACTIVE, LoanStatus.OVERDUE]
    active_loans_count_res = await db.execute(
        select(func.count(Loan.id)).filter(Loan.status.in_(active_statuses))
    )
    active_loans = active_loans_count_res.scalar() or 0

    # Total of loan amounts for active loans
    total_loan_amounts_res = await db.execute(
        select(func.coalesce(func.sum(Loan.total_amount), 0.0)).filter(Loan.status.in_(active_statuses))
    )
    total_loan_amounts = float(total_loan_amounts_res.scalar() or 0.0)

    # Total of installments paid against active loans
    total_installments_res = await db.execute(
        select(func.coalesce(func.sum(func.coalesce(Installment.amount, 0.0)), 0.0))
        .select_from(Installment)
        .join(Loan, Loan.id == Installment.loan_id)
        .filter(Loan.status.in_(active_statuses))
    )
    total_installments_paid = float(total_installments_res.scalar() or 0.0)

    active_loans_outstanding = max(0.0, total_loan_amounts - total_installments_paid)

    # Aliases counts and outstanding
    active_aliases_count_res = await db.execute(
        select(func.count(Alias.id)).filter(Alias.is_cleared == False)
    )
    active_aliases = active_aliases_count_res.scalar() or 0

    aliases_outstanding_res = await db.execute(
        select(func.coalesce(func.sum(Alias.remaining_amount), 0.0)).filter(Alias.is_cleared == False)
    )
    aliases_outstanding = float(aliases_outstanding_res.scalar() or 0.0)

    return {
        "active_loans": active_loans,
        "active_loans_outstanding": round(active_loans_outstanding, 2),
        "active_aliases": active_aliases,
        "active_aliases_outstanding": round(aliases_outstanding, 2),
    }


@router.get("/summary")
async def get_dashboard_summary(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Return high-level summary figures for the dashboard side panel.
    - Total amount of completed loans in the current month
    - Active loans (count) started in the current month
    - Total interest amount gained in the last three months
    - Total aliases created in the last three months (count)
    """
    today = datetime.now().date()
    month_start = today.replace(day=1)

    # Completed loans amount in current month
    completed_res = await db.execute(
        select(func.coalesce(func.sum(Loan.total_amount), 0.0))
        .filter(
            Loan.status == LoanStatus.COMPLETED,
            Loan.completed_at.isnot(None),
            func.date(Loan.completed_at) >= month_start,
            func.date(Loan.completed_at) <= today,
        )
    )
    completed_loans_amount_this_month = float(completed_res.scalar() or 0.0)

    # Active loans count started this month
    active_this_month_res = await db.execute(
        select(func.count(Loan.id)).filter(
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE]),
            Loan.start_date >= month_start,
            Loan.start_date <= today,
        )
    )
    active_loans_count_this_month = int(active_this_month_res.scalar() or 0)

    # Interest gained last 3 months: sum of interest for loans started in window
    last3_start = today - timedelta(days=90)
    interest_res = await db.execute(
        select(func.coalesce(func.sum(Loan.amount * (Loan.interest_rate / 100.0)), 0.0)).filter(
            Loan.start_date >= last3_start,
            Loan.start_date <= today,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.COMPLETED, LoanStatus.OVERDUE])
        )
    )
    interest_last_three_months = float(interest_res.scalar() or 0.0)

    # Aliases created in last 3 months (count)
    aliases_last3_res = await db.execute(
        select(func.count(Alias.id)).filter(
            Alias.alias_date >= last3_start,
            Alias.alias_date <= today,
        )
    )
    aliases_count_last_three_months = int(aliases_last3_res.scalar() or 0)

    return {
        "completed_loans_amount_this_month": round(completed_loans_amount_this_month, 2),
        "active_loans_count_this_month": active_loans_count_this_month,
        "interest_last_three_months": round(interest_last_three_months, 2),
        "aliases_count_last_three_months": aliases_count_last_three_months,
    }


@router.get("/trends")
async def get_trends(
    months: int = 3,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get returns and interest trends for the last N months"""
    
    # Calculate date range
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=months * 30)
    
    # Initialize result structure
    trends = []
    current = start_date
    
    while current <= end_date:
        # Get month start and end
        month_start = date(current.year, current.month, 1)
        if current.month == 12:
            month_end = date(current.year, 12, 31)
        else:
            month_end = date(current.year, current.month + 1, 1) - timedelta(days=1)
        
        # Get loans in this month
        loans_result = await db.execute(
            select(Loan).filter(
                and_(
                    Loan.start_date >= month_start,
                    Loan.start_date <= month_end,
                    Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.COMPLETED])
                )
            )
        )
        loans = loans_result.scalars().all()
        
        # Calculate returns (total amount of active/completed loans)
        returns = sum(loan.total_amount for loan in loans)
        
        # Calculate interest (total interest earned)
        interest = sum(loan.amount * (loan.interest_rate / 100) for loan in loans)
        
        trends.append({
            "month": current.strftime("%b"),
            "returns": round(returns, 2),
            "interest": round(interest, 2)
        })
        
        # Move to next month
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    
    return {
        "trends": trends
    }


@router.get("/recent-activity")
async def get_recent_activity(
    limit: int = 10,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Get recent loans and payments"""
    
    # Get recent loans
    loans_result = await db.execute(
        select(Loan).order_by(Loan.created_at.desc()).limit(limit)
    )
    loans = loans_result.scalars().all()
    
    activities = []
    for loan in loans:
        activities.append({
            "type": "loan",
            "id": loan.id,
            "customer_id": loan.customer_id,
            "amount": loan.amount,
            "status": loan.status.value,
            "date": loan.created_at
        })
    
    return activities

