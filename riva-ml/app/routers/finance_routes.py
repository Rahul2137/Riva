"""
Finance Routes v2 - REST API for financial data.

New in v2:
  - DELETE /finance/transactions/{id} — delete an expense
  - PATCH  /finance/transactions/{id} — update an expense
  - GET    /finance/budgets            — get full budget profile JSON
  - POST   /finance/budgets            — set/update a category budget
  - DELETE /finance/budgets/{category} — remove a category budget
  - GET    /finance/budgets/status     — compare spending vs budgets this month
  - POST   /finance/budgets/refine     — trigger AI auto-refinement
"""
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId, errors as bson_errors

from services.db import (
    add_transaction,
    get_transactions,
    get_spending_summary,
    transactions_collection,
    budgets_collection,
)
from services.budget_service import BudgetService

router = APIRouter(prefix="/finance", tags=["Finance"])

_budget_svc = BudgetService(budgets_collection, transactions_collection)


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


class TransactionUpdate(BaseModel):
    amount: Optional[float] = None
    category: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None


class BudgetSet(BaseModel):
    category: str
    limit: float


class TotalBudgetSet(BaseModel):
    limit: float


class SummaryResponse(BaseModel):
    total_income: float
    total_expense: float
    balance: float
    categories: dict
    period: dict


# ----------------------------
# Transaction Endpoints
# ----------------------------

@router.get("/transactions")
async def list_transactions(
    user_id: str = Query(...),
    days: int = Query(30),
    category: Optional[str] = None,
    type: Optional[str] = None,
    limit: int = Query(50, le=200),
):
    """Get user's transactions with optional filters."""
    start_date = datetime.utcnow() - timedelta(days=days)
    transactions = await get_transactions(
        user_id=user_id,
        start_date=start_date,
        category=category,
        transaction_type=type,
        limit=limit,
    )
    formatted = []
    for t in transactions:
        formatted.append({
            "id":           t["_id"],
            "type":         t["type"],
            "amount":       t["amount"],
            "category":     t["category"],
            "subcategory":  t.get("subcategory"),
            "description":  t.get("description"),
            "merchant":     t.get("merchant"),
            "payment_method": t.get("payment_method"),
            "date": t["date"].isoformat() if isinstance(t["date"], datetime) else t.get("date", ""),
        })
    return {"transactions": formatted, "count": len(formatted)}


@router.post("/transactions")
async def create_transaction(
    user_id: str = Query(...),
    transaction: TransactionCreate = None,
):
    """Manually add a transaction."""
    date = None
    if transaction.date:
        try:
            date = datetime.fromisoformat(transaction.date)
        except Exception:
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
        date=date,
    )
    return {"message": "Transaction added", "id": transaction_id}


@router.patch("/transactions/{transaction_id}")
async def update_transaction(
    transaction_id: str,
    user_id: str = Query(...),
    updates: TransactionUpdate = None,
):
    """Update fields of an existing transaction."""
    try:
        oid = ObjectId(transaction_id)
    except bson_errors.InvalidId:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")

    update_data: Dict[str, Any] = {}
    if updates.amount is not None:
        update_data["amount"] = updates.amount
    if updates.category is not None:
        update_data["category"] = updates.category.lower()
    if updates.description is not None:
        update_data["description"] = updates.description
    if updates.date is not None:
        update_data["date"] = updates.date
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    update_data["updated_at"] = datetime.utcnow()
    result = await transactions_collection.update_one(
        {"_id": oid, "user_id": user_id},
        {"$set": update_data},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction updated"}


@router.delete("/transactions/{transaction_id}")
async def delete_transaction(
    transaction_id: str,
    user_id: str = Query(...),
):
    """Delete a transaction by ID."""
    try:
        oid = ObjectId(transaction_id)
    except bson_errors.InvalidId:
        raise HTTPException(status_code=400, detail="Invalid transaction ID")

    result = await transactions_collection.delete_one({"_id": oid, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"message": "Transaction deleted"}


@router.get("/summary")
async def get_summary(
    user_id: str = Query(...),
    days: int = Query(30),
):
    """Get spending summary with category breakdown."""
    start_date = datetime.utcnow() - timedelta(days=days)
    summary = await get_spending_summary(user_id, start_date)
    return summary


# ----------------------------
# Budget Endpoints
# ----------------------------

@router.get("/budgets")
async def get_budget_profile(user_id: str = Query(...)):
    """Get the full budget profile JSON for this user."""
    profile = await _budget_svc.get_budget_profile(user_id)
    return profile


@router.post("/budgets")
async def set_category_budget(
    user_id: str = Query(...),
    body: BudgetSet = None,
):
    """Set or update the monthly budget for a category."""
    profile = await _budget_svc.set_category_budget(user_id, body.category, body.limit)
    return {"message": f"Budget set for {body.category}", "profile": profile}


@router.post("/budgets/total")
async def set_total_budget(
    user_id: str = Query(...),
    body: TotalBudgetSet = None,
):
    """Set the overall monthly spending cap."""
    profile = await _budget_svc.set_total_limit(user_id, body.limit)
    return {"message": "Total budget set", "profile": profile}


@router.delete("/budgets/{category}")
async def delete_category_budget(
    category: str,
    user_id: str = Query(...),
):
    """Remove a category from the budget profile."""
    deleted = await _budget_svc.delete_category_budget(user_id, category)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"No budget found for category '{category}'")
    return {"message": f"Budget for '{category}' removed"}


@router.get("/budgets/status")
async def get_budget_status(user_id: str = Query(...)):
    """
    Compare this month's actual spending vs budget limits.
    Returns per-category status (ok / warning / over) and warnings list.
    """
    # Get this month's spending
    now = datetime.utcnow()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    pipeline = [
        {"$match": {
            "user_id": user_id,
            "type": "expense",
            "$or": [
                {"created_at": {"$gte": start}},
                {"date": {"$gte": start.strftime("%Y-%m-%d")}},
            ],
        }},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}},
    ]
    cursor = transactions_collection.aggregate(pipeline)
    rows = await cursor.to_list(length=50)
    spending = {r["_id"]: r["total"] for r in rows}

    status = await _budget_svc.get_budget_status(user_id, spending)
    return status


@router.post("/budgets/refine")
async def refine_budgets(
    user_id: str = Query(...),
    months: int = Query(3, ge=1, le=12),
    apply: bool = Query(False, description="If true, auto-apply the suggestions"),
):
    """
    Use AI to analyse real spending history and suggest refined budget limits.
    Set ?apply=true to automatically apply the suggestions.
    """
    suggestions_data = await _budget_svc.refine_budgets_from_spending(user_id, months)
    if not suggestions_data:
        return {
            "message": f"Not enough spending data (need at least {months} months).",
            "suggestions": None,
        }

    if apply:
        profile = await _budget_svc.apply_ai_refinement(
            user_id, suggestions_data["suggestions"]
        )
        return {
            "message": "Budgets refined and applied!",
            "suggestions": suggestions_data["suggestions"],
            "profile": profile,
        }

    return {
        "message": f"Suggestions based on {months} months of spending. Call with ?apply=true to apply.",
        "suggestions": suggestions_data["suggestions"],
        "months_analysed": suggestions_data["months_analysed"],
    }


# ----------------------------
# Category Metadata
# ----------------------------

@router.get("/categories")
async def get_categories():
    """Get list of valid transaction categories with metadata."""
    return {
        "categories": [
            {"id": "food",          "name": "Food & Dining",       "icon": "🍔", "color": "#F97316"},
            {"id": "transport",     "name": "Transport",            "icon": "🚗", "color": "#3B82F6"},
            {"id": "shopping",      "name": "Shopping",             "icon": "🛍️", "color": "#EC4899"},
            {"id": "bills",         "name": "Bills & Utilities",    "icon": "📄", "color": "#EF4444"},
            {"id": "entertainment", "name": "Entertainment",        "icon": "🎬", "color": "#8B5CF6"},
            {"id": "health",        "name": "Health",               "icon": "❤️",  "color": "#10B981"},
            {"id": "personal",      "name": "Personal Care",        "icon": "✂️",  "color": "#F59E0B"},
            {"id": "salary",        "name": "Salary & Income",      "icon": "💰", "color": "#14B8A6"},
            {"id": "investment",    "name": "Investment",           "icon": "📈", "color": "#6366F1"},
            {"id": "other",         "name": "Other",                "icon": "📦", "color": "#6B7280"},
        ]
    }
