"""
Finance Manager - AI-powered financial tracking and coaching.
Uses synchronous PyMongo to avoid asyncio event loop conflicts.
"""
import os
from datetime import datetime, timedelta
from typing import Optional
from pydantic import BaseModel
from openai import OpenAI
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

# Define structured response model for transaction parsing
class FinanceActionResponse(BaseModel):
    action: str  # 'add', 'query', 'budget', 'error'
    responseToUser: str
    transaction_type: Optional[str] = None  # 'income' or 'expense'
    amount: Optional[float] = None
    category: Optional[str] = None
    subcategory: Optional[str] = None
    merchant: Optional[str] = None
    description: Optional[str] = None
    date: Optional[str] = None
    payment_method: Optional[str] = None


# Category mapping for normalization
VALID_CATEGORIES = [
    "food", "transport", "shopping", "bills", 
    "entertainment", "health", "salary", "investment", "other"
]


class FinanceManager:
    """Handles financial transactions and AI-powered insights."""
    
    def __init__(self):
        self.openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self._mongo_client = None
        self._db = None
    
    def _get_db(self):
        """Get MongoDB database connection (lazy initialization)."""
        if self._mongo_client is None:
            self._mongo_client = MongoClient(os.getenv("MONGO_URI"))
            self._db = self._mongo_client["riva"]
        return self._db
    
    def process_request(self, client, description: str, user_input: str, user_id: str = None) -> str:
        """
        Process financial voice command (fully synchronous).
        Returns response message to speak to user.
        """
        # Get financial context for AI coaching
        financial_context = ""
        if user_id:
            financial_context = self._get_financial_context(user_id)
        
        # Build messages for OpenAI
        system_prompt = f"""You are RIVA, an AI financial assistant. Analyze user input and determine the action.

ACTIONS:
- 'add': User wants to log a transaction (expense or income)
- 'query': User wants spending analysis, insights, or advice
- 'error': Input is unclear

For 'add' action, extract:
- transaction_type: 'expense' or 'income'
- amount: numeric value
- category: one of {VALID_CATEGORIES}
- subcategory: optional (e.g., 'coffee', 'uber', 'netflix')
- merchant: optional (store/brand name if mentioned)
- description: brief note
- payment_method: 'upi', 'cash', 'card', 'other'

For 'query' action, use this financial context to provide insights:
{financial_context if financial_context else "No financial history yet."}

Always be encouraging and provide actionable advice. Keep responseToUser concise (1-2 sentences)."""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Description: {description}. User said: {user_input}"}
        ]
        
        try:
            response = client.beta.chat.completions.parse(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.5,
                max_tokens=200,
                response_format=FinanceActionResponse
            )
            
            parsed = response.choices[0].message.parsed
            
            if parsed.action == "add" and parsed.amount and user_id:
                # Save transaction to database
                success = self._save_transaction(
                    user_id=user_id,
                    transaction_type=parsed.transaction_type or "expense",
                    amount=parsed.amount,
                    category=self._normalize_category(parsed.category),
                    subcategory=parsed.subcategory,
                    merchant=parsed.merchant,
                    description=parsed.description or user_input,
                    payment_method=parsed.payment_method or "other",
                    date=self._parse_date(parsed.date)
                )
                if not success:
                    return "Sorry, I couldn't save the transaction. Please try again."
            
            return parsed.responseToUser
            
        except Exception as e:
            print(f"[FINANCE] OpenAI Error: {e}")
            return "I couldn't process your financial request. Please try again."
    
    def _get_financial_context(self, user_id: str) -> str:
        """Get financial context as a string for AI coaching (sync)."""
        try:
            db = self._get_db()
            start_date = datetime.utcnow() - timedelta(days=30)
            
            # Get recent transactions
            transactions = list(db["transactions"].find(
                {"user_id": user_id, "date": {"$gte": start_date}}
            ).sort("date", -1).limit(20))
            
            if not transactions:
                return ""
            
            # Calculate totals
            total_expense = sum(t["amount"] for t in transactions if t.get("type") == "expense")
            total_income = sum(t["amount"] for t in transactions if t.get("type") == "income")
            
            # Category breakdown
            categories = {}
            for t in transactions:
                if t.get("type") == "expense":
                    cat = t.get("category", "other")
                    categories[cat] = categories.get(cat, 0) + t["amount"]
            
            context = f"""
User's Financial Summary (Last 30 days):
- Total Income: ₹{total_income:,.2f}
- Total Expenses: ₹{total_expense:,.2f}
- Balance: ₹{total_income - total_expense:,.2f}

Spending by Category:
"""
            for cat, amount in sorted(categories.items(), key=lambda x: -x[1]):
                context += f"- {cat.title()}: ₹{amount:,.2f}\n"
            
            context += f"\nRecent Transactions ({len(transactions)}):\n"
            for t in transactions[:5]:
                date_str = t["date"].strftime("%b %d") if isinstance(t["date"], datetime) else str(t["date"])[:10]
                context += f"- {date_str}: {t['type']} ₹{t['amount']:,.2f} ({t.get('category', 'other')})\n"
            
            return context
        except Exception as e:
            print(f"[FINANCE] Context error: {e}")
            return ""
    
    def _save_transaction(
        self,
        user_id: str,
        transaction_type: str,
        amount: float,
        category: str,
        subcategory: str = None,
        merchant: str = None,
        description: str = "",
        payment_method: str = "other",
        date: datetime = None
    ) -> bool:
        """Save a transaction to MongoDB (sync)."""
        try:
            db = self._get_db()
            transaction = {
                "user_id": user_id,
                "type": transaction_type,
                "amount": amount,
                "currency": "INR",
                "category": category.lower() if category else "other",
                "subcategory": subcategory.lower() if subcategory else None,
                "description": description,
                "merchant": merchant,
                "payment_method": payment_method,
                "is_recurring": False,
                "date": date or datetime.utcnow(),
                "created_at": datetime.utcnow()
            }
            result = db["transactions"].insert_one(transaction)
            print(f"[FINANCE] Saved: {transaction_type} ₹{amount} ({category}) - ID: {result.inserted_id}")
            return True
        except Exception as e:
            print(f"[FINANCE] Save error: {e}")
            return False
    
    def _normalize_category(self, category: str) -> str:
        """Normalize category to valid values."""
        if not category:
            return "other"
        category = category.lower().strip()
        if category in VALID_CATEGORIES:
            return category
        # Map common aliases
        aliases = {
            "food": ["restaurant", "groceries", "eating", "dining", "coffee", "lunch", "dinner"],
            "transport": ["uber", "ola", "taxi", "fuel", "petrol", "gas", "metro", "bus"],
            "shopping": ["clothes", "amazon", "flipkart", "electronics"],
            "bills": ["rent", "electricity", "water", "internet", "phone", "recharge"],
            "entertainment": ["movie", "netflix", "spotify", "games", "concert"],
            "health": ["medicine", "doctor", "hospital", "gym", "pharmacy"],
            "salary": ["income", "payment", "bonus", "freelance"],
        }
        for cat, keywords in aliases.items():
            if category in keywords:
                return cat
        return "other"
    
    def _parse_date(self, date_str: str) -> datetime:
        """Parse date string or return current datetime."""
        if not date_str:
            return datetime.utcnow()
        try:
            for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]:
                try:
                    return datetime.strptime(date_str, fmt)
                except ValueError:
                    continue
        except:
            pass
        return datetime.utcnow()
