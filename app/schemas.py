from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, date
from enum import Enum


# ----------------------------------------------------
# AUTH SCHEMAS
# ----------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str


# ----------------------------------------------------
# ENUMS
# ----------------------------------------------------
class LoanStatusEnum(str, Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    ALIASED = "aliased"


# ----------------------------------------------------
# CUSTOMER SCHEMAS
# ----------------------------------------------------
class CustomerBase(BaseModel):
    name: str
    id_number: str
    phone: str
    email: Optional[str] = None
    location: Optional[str] = None


class CustomerCreate(CustomerBase):
    pass


class CustomerResponse(CustomerBase):
    id: int
    created_at: datetime

    class Config:
        orm_mode = True


class CustomerCheckRequest(BaseModel):
    customer_id: Optional[int] = None
    id_number: Optional[str] = None


class CustomerCheck(BaseModel):
    exists: bool
    has_active_loan: bool
    has_active_alias: bool
    customer: Optional[CustomerResponse] = None

    class Config:
        orm_mode = True


# ----------------------------------------------------
# LOAN SCHEMAS
# ----------------------------------------------------
class LoanBase(BaseModel):
    id_number: str
    amount: float
    interest_rate: float
    start_date: date


class LoanCreate(LoanBase):
    pass


class LoanResponse(BaseModel):
    id: int
    customer_id: str   # ✅ match the DB column
    amount: float
    interest_rate: float
    total_amount: float
    start_date: date
    due_date: date
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None

    class Config:
        orm_mode = True


# ----------------------------------------------------
# INSTALLMENT SCHEMAS
# ----------------------------------------------------
class InstallmentResponse(BaseModel):
    id: int
    loan_id: int
    amount: float
    payment_date: datetime
    created_at: datetime

    class Config:
        orm_mode = True


# ----------------------------------------------------
# ALIAS SCHEMAS
# ----------------------------------------------------
class AliasResponse(BaseModel):
    id: int
    loan_id: int
    customer_id: int
    original_amount: float
    remaining_amount: float
    alias_date: date
    is_cleared: bool
    cleared_date: Optional[datetime]
    created_at: datetime

    class Config:
        orm_mode = True
