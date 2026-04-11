"""
FinanceAgent - Handles all money-related intents.

Consolidates the previous money_agent.py and finance_manager.py
into a single agent behind the BaseAgent interface.

Intents handled:
- add_expense, add_income, set_budget
- query_spending, query_income
- correction, dont_track

All DB operations use async Motor (no sync PyMongo).
"""
from datetime import datetime
from typing import Dict, Any, List, Optional
from openai import OpenAI
import os
import json
from dotenv import load_dotenv

from .base_agent import BaseAgent, AgentResponse

load_dotenv()

# Valid expense categories (shared with finance_routes.py)
VALID_CATEGORIES = [
    "food", "transport", "shopping", "bills",
    "entertainment", "health", "personal", "other",
]

# Category aliases for normalisation
CATEGORY_ALIASES = {
    "food": ["restaurant", "groceries", "eating", "dining", "coffee", "lunch", "dinner", "breakfast", "snack"],
    "transport": ["uber", "ola", "taxi", "fuel", "petrol", "gas", "metro", "bus", "train", "auto"],
    "shopping": ["clothes", "amazon", "flipkart", "electronics", "online"],
    "bills": ["rent", "electricity", "water", "internet", "phone", "recharge", "wifi"],
    "entertainment": ["movie", "netflix", "spotify", "games", "concert", "party", "outing"],
    "health": ["medicine", "doctor", "hospital", "gym", "pharmacy", "yoga"],
    "personal": ["haircut", "salon", "grooming", "laundry"],
}


class FinanceAgent(BaseAgent):
    """GPT-powered agent for all finance operations."""

    SUPPORTED_INTENTS = [
        "add_expense",
        "add_income",
        "set_budget",
        "query_spending",
        "query_income",
        "correction",
        "dont_track",
    ]

    def __init__(
        self,
        openai_client: OpenAI = None,
        transactions_collection=None,
        memory_service=None,
    ):
        self.client = openai_client or OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        self.transactions = transactions_collection
        self.memory_service = memory_service

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    @property
    def domain(self) -> str:
        return "money"

    def get_supported_intents(self) -> List[str]:
        return self.SUPPORTED_INTENTS

    async def handle(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Route to the appropriate handler based on intent."""
        print(f"[FINANCE_AGENT] Handling intent={intent}")

        if intent in ("add_expense", "add_income"):
            return await self._handle_add_transaction(intent, user_input, context, memory)
        elif intent == "set_budget":
            return await self._handle_set_budget(user_input, context, memory)
        elif intent in ("query_spending", "query_income"):
            return await self._handle_query(intent, user_input, context, memory)
        elif intent == "correction":
            return await self._handle_correction(user_input, context, memory)
        elif intent == "dont_track":
            return AgentResponse(
                response="No problem, I won't track that.",
                actions_taken=[],
            )
        else:
            return AgentResponse(response="I'm not sure how to handle that finance request.")

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    async def _handle_add_transaction(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Add an expense or income.

        Uses GPT to extract amount, category, description, date from
        the user's natural language input + session context.
        """
        extraction = await self._extract_transaction_data(user_input, context, memory)

        amount = extraction.get("amount")
        category = extraction.get("category")
        description = extraction.get("description", "")
        date_str = extraction.get("date", datetime.now().strftime("%Y-%m-%d"))
        needs_clarification = extraction.get("needs_clarification", False)
        clarification_question = extraction.get("clarification_question", "")

        # If we're missing critical data, ask for it
        if needs_clarification or amount is None:
            pending_field = "amount" if amount is None else "category"
            return AgentResponse(
                response=clarification_question or f"What was the {pending_field}?",
                requires_followup=True,
                pending_field=pending_field,
                data={"partial_data": extraction},
            )

        # Normalise category
        category = self._normalise_category(category)
        tx_type = "income" if intent == "add_income" else "expense"

        # Save to DB
        action_result = None
        if self.transactions is not None:
            try:
                transaction = {
                    "user_id": context.get("user_id", "unknown"),
                    "type": tx_type,
                    "amount": float(amount),
                    "currency": "INR",
                    "category": category,
                    "description": description,
                    "date": date_str,
                    "created_at": datetime.utcnow(),
                }
                await self.transactions.insert_one(transaction)
                action_result = f"{tx_type}_added"
                print(f"[FINANCE_AGENT] Saved {tx_type}: {amount} ({category})")
            except Exception as e:
                print(f"[FINANCE_AGENT] DB error: {e}")
                return AgentResponse(
                    response="Sorry, I couldn't save that. Please try again.",
                    metadata={"error": str(e)},
                )

        response_text = extraction.get(
            "response",
            f"Got it! Added ₹{amount:,.0f} for {description or category}.",
        )

        return AgentResponse(
            response=response_text,
            actions_taken=[action_result] if action_result else [],
            data={"amount": amount, "category": category, "type": tx_type},
        )

    async def _handle_set_budget(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Set a budget for a category or overall."""
        extraction = await self._extract_transaction_data(user_input, context, memory)

        amount = extraction.get("amount")
        category = extraction.get("category")

        if amount is None:
            return AgentResponse(
                response="How much would you like to set as the budget?",
                requires_followup=True,
                pending_field="amount",
            )

        # Save budget via memory service
        if self.memory_service:
            try:
                await self.memory_service.set_budget(
                    user_id=context.get("user_id", "unknown"),
                    amount=float(amount),
                    category=category,
                )
            except Exception as e:
                print(f"[FINANCE_AGENT] Budget save error: {e}")

        cat_label = category.title() if category else "overall"
        return AgentResponse(
            response=f"Budget set! I'll track your {cat_label} spending against ₹{amount:,.0f}/month.",
            actions_taken=["budget_set"],
            data={"amount": amount, "category": category},
        )

    async def _handle_query(
        self,
        intent: str,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Query spending or income data."""
        if self.transactions is None:
            return AgentResponse(response="Finance tracking isn't set up yet.")

        # Use GPT to understand what the user wants to query
        query_spec = await self._build_query_spec(user_input, context)

        # Build and run the MongoDB query
        from services.query_builder import QueryBuilder
        user_id = context.get("user_id", "unknown")
        builder = QueryBuilder(user_id)

        try:
            query = builder.build_query(query_spec)
            cursor = self.transactions.find(query)
            transactions = await cursor.to_list(length=100)

            if not transactions:
                return AgentResponse(
                    response="No transactions found for that period.",
                    data={"total": 0, "count": 0},
                )

            # Aggregate results
            total = sum(t.get("amount", 0) for t in transactions)
            by_category = {}
            for t in transactions:
                cat = t.get("category", "other")
                by_category[cat] = by_category.get(cat, 0) + t.get("amount", 0)

            query_results = {
                "total": total,
                "count": len(transactions),
                "by_category": by_category,
                "date_range": query_spec.get("date_range", "this_month"),
            }

            # Generate natural-language response via GPT
            response_text = await self._generate_query_response(
                user_input, intent, query_results, memory
            )

            return AgentResponse(
                response=response_text,
                data=query_results,
            )

        except Exception as e:
            print(f"[FINANCE_AGENT] Query error: {e}")
            return AgentResponse(
                response="I had trouble fetching your data. Please try again.",
                metadata={"error": str(e)},
            )

    async def _handle_correction(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> AgentResponse:
        """Handle corrections to previous transactions."""
        return AgentResponse(
            response="Transaction corrections are coming soon. For now, you can add a new entry.",
            metadata={"stub": True},
        )

    # ------------------------------------------------------------------
    # GPT helpers
    # ------------------------------------------------------------------

    async def _extract_transaction_data(
        self,
        user_input: str,
        context: Dict[str, Any],
        memory: Dict[str, Any],
    ) -> Dict:
        """Use GPT to extract structured transaction data from natural language."""
        context_parts = [f"Current date/time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"]

        if context.get("last_topic"):
            context_parts.append(f"Last topic: {context['last_topic']}")
        if context.get("last_category"):
            context_parts.append(f"Last category: {context['last_category']}")
        if context.get("pending_question"):
            context_parts.append(f"Waiting for answer to: {context['pending_question']}")
            if context.get("pending_data"):
                context_parts.append(f"Partial data: {json.dumps(context['pending_data'])}")
        if context.get("recent_messages"):
            recent = context["recent_messages"][-3:]
            for msg in recent:
                context_parts.append(f"  {msg['role']}: {msg['content']}")

        if memory.get("constraints"):
            context_parts.append(f"User budgets: {memory['constraints']}")

        context_str = "\n".join(context_parts)

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._extraction_prompt()},
                    {"role": "user", "content": f"CONTEXT:\n{context_str}\n\nUSER SAYS:\n{user_input}"},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
                max_tokens=400,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[FINANCE_AGENT] Extraction error: {e}")
            return {"needs_clarification": True, "clarification_question": "Sorry, could you repeat that?"}

    async def _build_query_spec(self, user_input: str, context: Dict) -> Dict:
        """Use GPT to build a query spec from natural language."""
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._query_prompt()},
                    {"role": "user", "content": user_input},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
                max_tokens=300,
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            print(f"[FINANCE_AGENT] Query spec error: {e}")
            return {"type": "expense", "date_range": "this_month"}

    async def _generate_query_response(
        self,
        user_input: str,
        intent: str,
        query_results: Dict,
        memory: Dict,
    ) -> str:
        """Generate a natural-language response for query results."""
        context_data = {
            "user_input": user_input,
            "intent": intent,
            "query_results": query_results,
            "current_date": datetime.now().strftime("%Y-%m-%d"),
        }
        if memory.get("constraints"):
            context_data["user_budgets"] = memory["constraints"]

        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": self._response_prompt()},
                    {"role": "user", "content": json.dumps(context_data, default=str)},
                ],
                temperature=0.5,
                max_tokens=300,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[FINANCE_AGENT] Response gen error: {e}")
            total = query_results.get("total", 0)
            return f"You've spent ₹{total:,.0f} so far."

    # ------------------------------------------------------------------
    # Prompts
    # ------------------------------------------------------------------

    def _extraction_prompt(self) -> str:
        return """You are RIVA's finance data extractor. Analyze user input and extract transaction data.

RETURN THIS JSON:
{
  "amount": number or null,
  "category": "food|transport|shopping|entertainment|bills|health|personal|other" or null,
  "description": "short description",
  "date": "YYYY-MM-DD",
  "needs_clarification": true/false,
  "clarification_question": "string or null",
  "response": "Natural confirmation message (e.g. 'Got it! Added ₹500 for dinner.')"
}

RULES:
- If amount is missing, set needs_clarification=true
- If category is missing but amount is present, set needs_clarification=true
- Use context (last_topic, pending_data) to fill in missing info
- Use ₹ for currency in response
- Keep response concise (1 sentence)
- TODAY'S DATE: """ + datetime.now().strftime("%Y-%m-%d")

    def _query_prompt(self) -> str:
        return """You are a query spec builder. Convert natural language into a MongoDB query spec.

RETURN THIS JSON:
{
  "type": "expense" | "income" | "all",
  "category": category or null,
  "date_range": "today|yesterday|this_week|last_week|this_month|last_month|last_30_days|all_time",
  "min_amount": number or null,
  "max_amount": number or null,
  "group_by": "category" | "day" | null,
  "sort_by": "amount" | "date" | null,
  "sort_order": "asc" | "desc",
  "limit": number or null
}"""

    def _response_prompt(self) -> str:
        return """You are RIVA. Given financial query results, generate a concise, friendly response.

RULES:
- Use ₹ for currency
- Be concise (1-2 sentences)
- If budget exists, mention how close user is to limit
- Be supportive, never judgmental
- Mention top categories if available"""

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_category(category: Optional[str]) -> str:
        """Normalise category string to a valid value."""
        if not category:
            return "other"
        category = category.lower().strip()
        if category in VALID_CATEGORIES:
            return category
        for valid_cat, aliases in CATEGORY_ALIASES.items():
            if category in aliases:
                return valid_cat
        return "other"
