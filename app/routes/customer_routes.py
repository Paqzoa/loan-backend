from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_
from sqlalchemy.future import select
from ..database import get_db
from ..models import Customer, Loan, Alias, LoanStatus
from ..schemas import CustomerCreate, CustomerResponse, CustomerCheck, CustomerCheckRequest
from typing import List
from ..auth import get_current_user

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/")
async def list_customers(
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """List customers with basic info (paginated)"""
    result = await db.execute(
        select(Customer).order_by(Customer.created_at.desc()).limit(limit).offset(offset)
    )
    return result.scalars().all()


@router.get("/by-id-number/{id_number}")
async def get_customer_by_id_number(
    id_number: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    result = await db.execute(select(Customer).filter(Customer.id_number == id_number))
    customer = result.scalar_one_or_none()
    if not customer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    loans_result = await db.execute(select(Loan).filter(Loan.customer_id == id_number))
    loans = loans_result.scalars().all()
    return {
        "id": customer.id,
        "name": customer.name,
        "id_number": customer.id_number,
        "phone": customer.phone,
        "email": customer.email,
        "location": customer.location,
        "created_at": customer.created_at,
        "loans": [
            {
                "id": loan.id,
                "amount": loan.amount,
                "interest_rate": loan.interest_rate,
                "total_amount": loan.total_amount,
                "start_date": loan.start_date,
                "due_date": loan.due_date,
                "status": loan.status.value,
                "created_at": loan.created_at,
            }
            for loan in loans
        ],
    }

@router.get("/{customer_id}")
async def get_customer_by_id(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Get customer by ID with loans and aliases"""
    result = await db.execute(select(Customer).filter(Customer.id == customer_id))
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )
    
    # Get customer loans
    loans_result = await db.execute(
        select(Loan).filter(Loan.customer_id == customer.id_number)
    )
    loans = loans_result.scalars().all()
    
    # Get customer aliases
    aliases_result = await db.execute(
        select(Alias).filter(Alias.customer_id == customer.id)
    )
    aliases = aliases_result.scalars().all()
    
    return {
        "id": customer.id,
        "name": customer.name,
        "id_number": customer.id_number,
        "phone": customer.phone,
        "email": customer.email,
        "location": customer.location,
        "created_at": customer.created_at,
        "loans": [
            {
                "id": loan.id,
                "amount": loan.amount,
                "interest_rate": loan.interest_rate,
                "total_amount": loan.total_amount,
                "start_date": loan.start_date,
                "due_date": loan.due_date,
                "status": loan.status.value,
                "created_at": loan.created_at
            } for loan in loans
        ],
        "aliases": [
            {
                "id": alias.id,
                "original_amount": alias.original_amount,
                "remaining_amount": alias.remaining_amount,
                "alias_date": alias.alias_date,
                "is_cleared": alias.is_cleared,
                "created_at": alias.created_at
            } for alias in aliases
        ]
    }


@router.post("/check", response_model=CustomerCheck)
async def check_customer_eligibility(
    request: CustomerCheckRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Check if customer exists and whether they have active loans or aliases"""
    # Determine lookup key
    customer = None
    if request.customer_id is not None:
        result = await db.execute(select(Customer).filter(Customer.id == request.customer_id))
        customer = result.scalar_one_or_none()
    elif request.id_number is not None:
        result = await db.execute(select(Customer).filter(Customer.id_number == request.id_number))
        customer = result.scalar_one_or_none()

    # If not found — just return False values (not an error)
    if not customer:
        return {
            "exists": False,
            "has_active_loan": False,
            "has_active_alias": False,
            "customer": None
        }

    # Check for active loans
    loan_result = await db.execute(
        select(Loan).filter(
            Loan.customer_id == customer.id,
            Loan.status.in_([LoanStatus.ACTIVE, LoanStatus.OVERDUE])
        )
    )
    active_loan = loan_result.scalar_one_or_none()

    # Check for active aliases
    alias_result = await db.execute(
        select(Alias).filter(
            Alias.customer_id == customer.id,
            Alias.is_cleared == False
        )
    )
    active_alias = alias_result.scalar_one_or_none()

    return {
        "exists": True,
        "has_active_loan": active_loan is not None,
        "has_active_alias": active_alias is not None,
        "customer": {
            "id": customer.id,
            "name": customer.name,
            "id_number": customer.id_number,
            "phone": customer.phone,
            "email": customer.email,
            "location": customer.location,
            "created_at": customer.created_at,
        }
    }



@router.post("/", response_model=CustomerResponse)
async def create_customer(
    customer: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a new customer"""
    # Check uniqueness for id_number and phone
    existing = await db.execute(
        select(Customer).filter(
            or_(
                Customer.id_number == customer.id_number,
                Customer.phone == customer.phone,
            )
        )
    )
    existing_customer = existing.scalar_one_or_none()
    if existing_customer:
        field = (
            "id_number" if existing_customer.id_number == customer.id_number else "phone"
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Customer with this {field} already exists",
        )

    db_customer = Customer(**customer.dict())
    db.add(db_customer)
    await db.commit()
    await db.refresh(db_customer)
    return db_customer


@router.get("/search", response_model=List[CustomerResponse])
async def search_customers(
    q: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Search customers by name, ID number, or phone"""
    if not q:
        return []
    
    result = await db.execute(
        select(Customer).filter(
            or_(
                Customer.name.ilike(f"%{q}%"),
                Customer.id_number.ilike(f"%{q}%"),
                Customer.phone.ilike(f"%{q}%")
            )
        ).limit(20)
    )
    return result.scalars().all()
