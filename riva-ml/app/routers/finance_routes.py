"""
Finance Routes - REST API for financial data.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime, timedelta
from services.db import (
    add_transaction, 
    get_transactions, 
    get_spending_summary,
    set_budget,
    get_budgets
)

router = APIRouter(prefix="/finance", tags=["Finance"])


# ----------------------------
# Request/Response Models
# ----------------------------
class TransactionCreate(BaseModel):
    type: str  # 'expense' or 'income'
    amount: float
    category: str
    subcategory: Optional[str] = None
    description: Optional[str] = None
    merchant: Optional[str] = None
    payment_method: Optional[str] = "other"
    date: Optional[str] = None


class TransactionResponse(BaseModel):
    id: str
    type: str
    amount: float
    category: str
    subcategory: Optional[str]
    description: Optional[str]
    merchant: Optional[str]
    date: str
    payment_method: Optional[str]


class BudgetCreate(BaseModel):
    category: str
    monthly_limit: float
    alert_threshold: Optional[float] = 0.8


class SummaryResponse(BaseModel):
    total_income: float
    total_expense: float
    balance: float
    categories: dict
    period: dict


# ----------------------------
# Endpoints
# ----------------------------

@router.get("/transactions")
async def list_transactions(
    user_id: str = Query(..., description="User ID"),
    days: int = Query(30, description="Number of days to fetch"),
    category: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(50, le=200)
):
    """Get user's transactions with optional filters."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    transactions = await get_transactions(
        user_id=user_id,
        start_date=start_date,
        category=category,
        transaction_type=type,
        limit=limit
    )
    
    # Format for response
    formatted = []
    for t in transactions:
        formatted.append({
            "id": t["_id"],
            "type": t["type"],
            "amount": t["amount"],
            "category": t["category"],
            "subcategory": t.get("subcategory"),
            "description": t.get("description"),
            "merchant": t.get("merchant"),
            "payment_method": t.get("payment_method"),
            "date": t["date"].isoformat() if isinstance(t["date"], datetime) else t["date"]
        })
    
    return {"transactions": formatted, "count": len(formatted)}


@router.post("/transactions")
async def create_transaction(
    user_id: str = Query(..., description="User ID"),
    transaction: TransactionCreate = None
):
    """Manually add a transaction."""
    date = None
    if transaction.date:
        try:
            date = datetime.fromisoformat(transaction.date)
        except:
            date = datetime.utcnow()
    
    transaction_id = await add_transaction(
        user_id=user_id,
        transaction_type=transaction.type,
        amount=transaction.amount,
        category=transaction.category,
        subcategory=transaction.subcategory,
        description=transaction.description,
        merchant=transaction.merchant,
        payment_method=transaction.payment_method,
        date=date
    )
    
    return {"message": "Transaction added", "id": transaction_id}


@router.get("/summary")
async def get_summary(
    user_id: str = Query(..., description="User ID"),
    days: int = Query(30, description="Number of days to summarize")
):
    """Get spending summary with category breakdown."""
    start_date = datetime.utcnow() - timedelta(days=days)
    summary = await get_spending_summary(user_id, start_date)
    return summary


@router.get("/budgets")
async def list_budgets(
    user_id: str = Query(..., description="User ID")
):
    """Get all budgets for a user."""
    budgets = await get_budgets(user_id)
    return {"budgets": budgets}


@router.post("/budgets")
async def create_budget(
    user_id: str = Query(..., description="User ID"),
    budget: BudgetCreate = None
):
    """Set or update a budget for a category."""
    result = await set_budget(
        user_id=user_id,
        category=budget.category,
        monthly_limit=budget.monthly_limit,
        alert_threshold=budget.alert_threshold
    )
    return {"message": result}


@router.get("/categories")
async def get_categories():
    """Get list of valid transaction categories."""
    return {
        "categories": [
            {"id": "food", "name": "Food & Dining", "icon": "🍔", "color": "#F97316"},
            {"id": "transport", "name": "Transport", "icon": "🚗", "color": "#3B82F6"},
            {"id": "shopping", "name": "Shopping", "icon": "🛍️", "color": "#EC4899"},
            {"id": "bills", "name": "Bills & Utilities", "icon": "📄", "color": "#EF4444"},
            {"id": "entertainment", "name": "Entertainment", "icon": "🎬", "color": "#8B5CF6"},
            {"id": "health", "name": "Health", "icon": "❤️", "color": "#10B981"},
            {"id": "salary", "name": "Salary & Income", "icon": "💰", "color": "#14B8A6"},
            {"id": "investment", "name": "Investment", "icon": "📈", "color": "#6366F1"},
            {"id": "other", "name": "Other", "icon": "📦", "color": "#6B7280"},
        ]
    }
