from sqlalchemy import Column, Integer, String, DateTime, Float, Boolean, ForeignKey, Date, Enum
from sqlalchemy.orm import relationship
from datetime import datetime, timedelta
import enum
from app.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    id_number = Column(String(30), unique=True, nullable=False)
    phone = Column(String(20), unique=True, nullable=False)
    email = Column(String(120), nullable=True)
    location = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    loans = relationship("Loan", back_populates="customer", cascade="all, delete-orphan")
    aliases = relationship("Alias", back_populates="customer", cascade="all, delete-orphan")

class LoanStatus(enum.Enum):
    ACTIVE = "active"
    COMPLETED = "completed"
    OVERDUE = "overdue"
    ALIASED = "aliased"

class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(String(30), ForeignKey("customers.id_number"), nullable=False)
    amount = Column(Float, nullable=False)
    interest_rate = Column(Float, default=20.0, nullable=False)  # 20% interest rate
    total_amount = Column(Float, nullable=False)  # Principal + Interest
    start_date = Column(Date, nullable=False, default=datetime.utcnow().date)
    due_date = Column(Date, nullable=False)
    status = Column(Enum(LoanStatus), default=LoanStatus.ACTIVE, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    customer = relationship("Customer", back_populates="loans")
    installments = relationship("Installment", back_populates="loan", cascade="all, delete-orphan")
    alias = relationship("Alias", back_populates="loan", uselist=False, cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        super(Loan, self).__init__(**kwargs)
        # Calculate total amount (principal + interest)
        if 'amount' in kwargs:
            interest = kwargs.get('amount') * (kwargs.get('interest_rate', 20.0) / 100)
            self.total_amount = kwargs.get('amount') + interest
        
        # Set due date (1 month from start date)
        if 'start_date' in kwargs:
            start = kwargs.get('start_date')
            # Add one month to the start date
            if isinstance(start, datetime):
                start = start.date()
            
            # Simple way to add a month (30 days)
            self.due_date = start + timedelta(days=30)
        elif not kwargs.get('due_date'):
            self.due_date = datetime.utcnow().date() + timedelta(days=30)

class Installment(Base):
    __tablename__ = "installments"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False)
    amount = Column(Float, nullable=False)
    payment_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationship
    loan = relationship("Loan", back_populates="installments")

class Alias(Base):
    __tablename__ = "aliases"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"), nullable=False, unique=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    original_amount = Column(Float, nullable=False)  # Original loan amount
    remaining_amount = Column(Float, nullable=False)  # Unpaid amount including interest
    alias_date = Column(Date, nullable=False, default=datetime.utcnow().date)
    is_cleared = Column(Boolean, default=False)
    cleared_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    loan = relationship("Loan", back_populates="alias")
    customer = relationship("Customer", back_populates="aliases")