"""
Database Module - MongoDB connection and collection references.
"""
from motor.motor_asyncio import AsyncIOMotorClient
from models.user.user_model import UserContextCache
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from bson import ObjectId

load_dotenv()

# Initialize MongoDB Client
client = AsyncIOMotorClient(os.getenv("MONGO_URI"))
db = client["riva"]

# ----------------------------
# Collection References
# ----------------------------
users_collection = db["users"]
transactions_collection = db["transactions"]
budgets_collection = db["budgets"]
financial_goals_collection = db["financial_goals"]

# Memory System Collections
user_memory_collection = db["user_memory"]          # Facts, preferences, habits
conversation_summary_collection = db["conversation_summary"]  # Compressed chat history
action_log_collection = db["action_log"]            # Audit trail

# Calendar System Collections
calendar_tokens_collection = db["calendar_tokens"]   # Per-user Google OAuth tokens


# ----------------------------
# User Context Functions
# ----------------------------
async def get_user_context(user_id: str) -> UserContextCache:
    doc = await db["UserContextCache"].find_one({"user_id": user_id})
    if not doc:
        raise ValueError(f"No context found for user_id {user_id}")
    return UserContextCache(**doc)


async def get_user_data_by_fields(user_id: str, fields: dict) -> dict:
    user_data = {}
    for collection_name, keys in fields.items():
        projection = {key: 1 for key in keys}
        projection["user_id"] = 1
        doc = await db[collection_name].find_one({"user_id": user_id}, projection)
        if doc:
            user_data[collection_name] = doc
    return user_data


# ----------------------------
# Transaction Functions
# ----------------------------
async def add_transaction(
    user_id: str,
    transaction_type: str,
    amount: float,
    category: str,
    description: str = "",
    subcategory: str = None,
    merchant: str = None,
    payment_method: str = "other",
    is_recurring: bool = False,
    date: datetime = None
) -> str:
    """Add a new transaction to the database."""
    transaction = {
        "user_id": user_id,
        "type": transaction_type,  # "expense" or "income"
        "amount": amount,
        "currency": "INR",
        "category": category.lower(),
        "subcategory": subcategory.lower() if subcategory else None,
        "description": description,
        "merchant": merchant,
        "payment_method": payment_method,
        "is_recurring": is_recurring,
        "date": date or datetime.utcnow(),
        "created_at": datetime.utcnow()
    }
    result = await transactions_collection.insert_one(transaction)
    return str(result.inserted_id)


async def get_transactions(
    user_id: str,
    start_date: datetime = None,
    end_date: datetime = None,
    category: str = None,
    transaction_type: str = None,
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Get transactions with optional filters."""
    query = {"user_id": user_id}
    
    if start_date or end_date:
        # Query both date (string) and created_at (datetime) fields
        date_filter = {}
        created_at_filter = {}
        
        if start_date:
            date_filter["$gte"] = start_date.strftime("%Y-%m-%d")
            created_at_filter["$gte"] = start_date
        if end_date:
            date_filter["$lte"] = end_date.strftime("%Y-%m-%d")
            created_at_filter["$lte"] = end_date
        
        # Match either date field (string) or created_at (datetime)
        query["$or"] = [
            {"date": date_filter},
            {"created_at": created_at_filter}
        ]
    
    if category:
        query["category"] = category.lower()
    
    if transaction_type:
        query["type"] = transaction_type
    
    cursor = transactions_collection.find(query).sort("created_at", -1).limit(limit)
    transactions = await cursor.to_list(length=limit)
    
    # Convert ObjectId to string for JSON serialization
    for t in transactions:
        t["_id"] = str(t["_id"])
    
    return transactions


async def get_spending_summary(
    user_id: str,
    start_date: datetime = None,
    end_date: datetime = None
) -> Dict[str, Any]:
    """Get spending summary with category breakdown."""
    if not start_date:
        start_date = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0)
    if not end_date:
        end_date = datetime.utcnow()
    
    # Aggregation pipeline for summary - match both date formats
    pipeline = [
        {
            "$match": {
                "user_id": user_id,
                "$or": [
                    {"date": {"$gte": start_date.strftime("%Y-%m-%d"), "$lte": end_date.strftime("%Y-%m-%d")}},
                    {"created_at": {"$gte": start_date, "$lte": end_date}}
                ]
            }
        },
        {
            "$group": {
                "_id": {"type": "$type", "category": "$category"},
                "total": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }
        }
    ]
    
    cursor = transactions_collection.aggregate(pipeline)
    results = await cursor.to_list(length=100)
    
    # Process results
    summary = {
        "total_income": 0,
        "total_expense": 0,
        "balance": 0,
        "categories": {},
        "period": {
            "start": start_date.isoformat(),
            "end": end_date.isoformat()
        }
    }
    
    for r in results:
        amount = r["total"]
        t_type = r["_id"]["type"]
        category = r["_id"]["category"]
        
        if t_type == "income":
            summary["total_income"] += amount
        else:
            summary["total_expense"] += amount
            if category not in summary["categories"]:
                summary["categories"][category] = 0
            summary["categories"][category] += amount
    
    summary["balance"] = summary["total_income"] - summary["total_expense"]
    
    return summary


async def get_financial_context(user_id: str, days: int = 30) -> str:
    """Get financial context as a string for AI coaching."""
    start_date = datetime.utcnow() - timedelta(days=days)
    
    # Get summary
    summary = await get_spending_summary(user_id, start_date)
    
    # Get recent transactions
    transactions = await get_transactions(user_id, start_date=start_date, limit=20)
    
    # Get budgets
    budgets = await budgets_collection.find({"user_id": user_id}).to_list(length=20)
    
    # Build context string
    context = f"""
User's Financial Summary (Last {days} days):
- Total Income: ₹{summary['total_income']:,.2f}
- Total Expenses: ₹{summary['total_expense']:,.2f}
- Balance: ₹{summary['balance']:,.2f}

Spending by Category:
"""
    for cat, amount in summary.get("categories", {}).items():
        context += f"- {cat.title()}: ₹{amount:,.2f}\n"
    
    if budgets:
        context += "\nBudgets:\n"
        for b in budgets:
            context += f"- {b['category'].title()}: ₹{b.get('monthly_limit', 0):,.2f}/month\n"
    
    if transactions:
        context += "\nRecent Transactions:\n"
        for t in transactions[:10]:
            date_str = t["date"].strftime("%b %d") if isinstance(t["date"], datetime) else t["date"]
            context += f"- {date_str}: {t['type']} ₹{t['amount']:,.2f} ({t['category']})\n"
    
    return context


# ----------------------------
# Budget Functions
# ----------------------------
async def set_budget(
    user_id: str,
    category: str,
    monthly_limit: float,
    alert_threshold: float = 0.8
) -> str:
    """Set or update a budget for a category."""
    result = await budgets_collection.update_one(
        {"user_id": user_id, "category": category.lower()},
        {
            "$set": {
                "monthly_limit": monthly_limit,
                "alert_threshold": alert_threshold,
                "updated_at": datetime.utcnow()
            },
            "$setOnInsert": {
                "created_at": datetime.utcnow()
            }
        },
        upsert=True
    )
    return "Budget updated" if result.modified_count else "Budget created"


async def get_budgets(user_id: str) -> List[Dict[str, Any]]:
    """Get all budgets for a user."""
    cursor = budgets_collection.find({"user_id": user_id})
    budgets = await cursor.to_list(length=50)
    for b in budgets:
        b["_id"] = str(b["_id"])
    return budgets
