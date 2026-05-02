"""
Budget Service — Manages user budget profiles.

Budget profiles are stored as a single JSON document per user in budgets_collection.
Structure:
{
  "user_id": "...",
  "monthly_budgets": {
    "food":          {"limit": 8000,  "icon": "🍔", "color": "#F97316"},
    "transport":     {"limit": 4000,  "icon": "🚗", "color": "#3B82F6"},
    "shopping":      {"limit": 5000,  "icon": "🛍️", "color": "#EC4899"},
    "bills":         {"limit": 6000,  "icon": "📄", "color": "#EF4444"},
    "entertainment": {"limit": 3000,  "icon": "🎬", "color": "#8B5CF6"},
    "health":        {"limit": 2000,  "icon": "❤️",  "color": "#10B981"},
    "personal":      {"limit": 2000,  "icon": "✂️",  "color": "#F59E0B"},
    "other":         {"limit": 2000,  "icon": "📦", "color": "#6B7280"},
  },
  "total_monthly_limit": null,  # optional overall cap
  "currency": "INR",
  "ai_refined": false,          # true once agent has adjusted based on spending data
  "last_refined_at": null,
  "updated_at": "...",
  "created_at": "...",
}

The agent can call `refine_budgets_from_spending()` to auto-adjust limits based
on 3+ months of real spending data.
"""
from datetime import datetime
from typing import Dict, Any, Optional, List

# ------------------------------------------------------------------
# Default budget profile (shown to new users)
# ------------------------------------------------------------------
DEFAULT_BUDGETS: Dict[str, Dict] = {
    "food":          {"limit": 8000,  "icon": "🍔", "color": "#F97316"},
    "transport":     {"limit": 4000,  "icon": "🚗", "color": "#3B82F6"},
    "shopping":      {"limit": 5000,  "icon": "🛍️", "color": "#EC4899"},
    "bills":         {"limit": 6000,  "icon": "📄", "color": "#EF4444"},
    "entertainment": {"limit": 3000,  "icon": "🎬", "color": "#8B5CF6"},
    "health":        {"limit": 2000,  "icon": "❤️",  "color": "#10B981"},
    "personal":      {"limit": 2000,  "icon": "✂️",  "color": "#F59E0B"},
    "other":         {"limit": 2000,  "icon": "📦", "color": "#6B7280"},
}

CATEGORY_META: Dict[str, Dict] = {
    "food":          {"icon": "🍔", "color": "#F97316"},
    "transport":     {"icon": "🚗", "color": "#3B82F6"},
    "shopping":      {"icon": "🛍️", "color": "#EC4899"},
    "bills":         {"icon": "📄", "color": "#EF4444"},
    "entertainment": {"icon": "🎬", "color": "#8B5CF6"},
    "health":        {"icon": "❤️",  "color": "#10B981"},
    "personal":      {"icon": "✂️",  "color": "#F59E0B"},
    "other":         {"icon": "📦", "color": "#6B7280"},
}


class BudgetService:
    """Manages per-user budget profiles in MongoDB."""

    def __init__(self, budgets_collection, transactions_collection=None):
        self.budgets = budgets_collection
        self.transactions = transactions_collection

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    async def get_budget_profile(self, user_id: str) -> Dict[str, Any]:
        """Return the user's full budget profile, seeding defaults if new."""
        doc = await self.budgets.find_one({"user_id": user_id})
        if not doc:
            doc = await self._seed_defaults(user_id)
        doc["_id"] = str(doc["_id"])
        return doc

    async def set_category_budget(
        self, user_id: str, category: str, limit: float
    ) -> Dict[str, Any]:
        """Set or update the budget for a single category."""
        category = category.lower().strip()
        meta = CATEGORY_META.get(category, {"icon": "📦", "color": "#6B7280"})
        now = datetime.utcnow()

        await self.budgets.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    f"monthly_budgets.{category}": {
                        "limit": float(limit),
                        "icon": meta["icon"],
                        "color": meta["color"],
                    },
                    "updated_at": now,
                },
                "$setOnInsert": {"created_at": now, "currency": "INR", "ai_refined": False},
            },
            upsert=True,
        )
        return await self.get_budget_profile(user_id)

    async def set_total_limit(self, user_id: str, limit: float) -> Dict[str, Any]:
        """Set the overall monthly spending cap."""
        await self.budgets.update_one(
            {"user_id": user_id},
            {"$set": {"total_monthly_limit": float(limit), "updated_at": datetime.utcnow()}},
            upsert=True,
        )
        return await self.get_budget_profile(user_id)

    async def delete_category_budget(self, user_id: str, category: str) -> bool:
        """Remove a category budget."""
        category = category.lower().strip()
        result = await self.budgets.update_one(
            {"user_id": user_id},
            {"$unset": {f"monthly_budgets.{category}": ""}, "$set": {"updated_at": datetime.utcnow()}},
        )
        return result.modified_count > 0

    # ------------------------------------------------------------------
    # Spending vs Budget comparison
    # ------------------------------------------------------------------

    async def get_budget_status(
        self, user_id: str, spending_by_category: Dict[str, float]
    ) -> Dict[str, Any]:
        """
        Compare current spending against budget limits.

        Returns:
            {
                "categories": {
                    "food": {
                        "limit": 8000, "spent": 5000, "remaining": 3000,
                        "pct": 0.625, "status": "ok|warning|over"
                    },
                    ...
                },
                "total_limit": 30000,
                "total_spent": 18000,
                "total_remaining": 12000,
                "warnings": ["food is at 87%", ...]
            }
        """
        profile = await self.get_budget_profile(user_id)
        monthly = profile.get("monthly_budgets", {})
        total_limit = profile.get("total_monthly_limit")

        result_cats = {}
        warnings = []
        total_spent_tracked = 0

        for cat, budget in monthly.items():
            limit = budget.get("limit", 0)
            spent = spending_by_category.get(cat, 0)
            remaining = max(0, limit - spent)
            pct = spent / limit if limit > 0 else 0
            total_spent_tracked += spent

            if pct >= 1.0:
                status = "over"
                warnings.append(f"{cat} budget exceeded ({int(pct*100)}%)")
            elif pct >= 0.8:
                status = "warning"
                warnings.append(f"{cat} at {int(pct*100)}% of budget")
            else:
                status = "ok"

            result_cats[cat] = {
                "limit": limit,
                "spent": spent,
                "remaining": remaining,
                "pct": round(pct, 3),
                "status": status,
                "icon": budget.get("icon", "📦"),
                "color": budget.get("color", "#6B7280"),
            }

        # Total check
        total_remaining = None
        if total_limit:
            total_all_spent = sum(spending_by_category.values())
            total_remaining = max(0, total_limit - total_all_spent)
            total_pct = total_all_spent / total_limit if total_limit > 0 else 0
            if total_pct >= 0.9:
                warnings.insert(0, f"Overall monthly budget at {int(total_pct*100)}%")

        return {
            "categories": result_cats,
            "total_limit": total_limit,
            "total_spent": total_spent_tracked,
            "total_remaining": total_remaining,
            "warnings": warnings,
            "currency": profile.get("currency", "INR"),
        }

    # ------------------------------------------------------------------
    # AI budget refinement
    # ------------------------------------------------------------------

    async def refine_budgets_from_spending(
        self, user_id: str, months_of_data: int = 3
    ) -> Optional[Dict[str, Any]]:
        """
        Analyse real spending patterns and suggest refined budget limits.

        Rule: new_limit = round(avg_monthly_spend * 1.15, -2)
              (15% buffer above actual average, rounded to nearest 100)

        Only refines categories where we have at least `months_of_data` months
        of history. Returns None if insufficient data.
        """
        if not self.transactions:
            return None

        from datetime import timedelta
        now = datetime.utcnow()
        start = now - timedelta(days=30 * months_of_data)

        # Pull all expenses in the window
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "type": "expense",
                    "$or": [
                        {"created_at": {"$gte": start}},
                        {"date": {"$gte": start.strftime("%Y-%m-%d")}},
                    ],
                }
            },
            {
                "$group": {
                    "_id": "$category",
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1},
                }
            },
        ]

        cursor = self.transactions.aggregate(pipeline)
        results = await cursor.to_list(length=50)

        if not results:
            return None

        profile = await self.get_budget_profile(user_id)
        current = profile.get("monthly_budgets", {})
        suggestions: Dict[str, Dict] = {}

        for r in results:
            cat = r["_id"]
            total = r["total"]
            # Average per month
            avg_monthly = total / months_of_data
            # 15% buffer, rounded to nearest 100
            suggested_limit = round(avg_monthly * 1.15 / 100) * 100

            if suggested_limit > 0:
                current_limit = current.get(cat, {}).get("limit", 0)
                change_pct = ((suggested_limit - current_limit) / current_limit * 100) if current_limit else 0
                suggestions[cat] = {
                    "current_limit": current_limit,
                    "suggested_limit": suggested_limit,
                    "avg_monthly_spend": round(avg_monthly, 2),
                    "change_pct": round(change_pct, 1),
                }

        return {
            "suggestions": suggestions,
            "months_analysed": months_of_data,
            "generated_at": now.isoformat(),
        }

    async def apply_ai_refinement(
        self, user_id: str, suggestions: Dict[str, Dict]
    ) -> Dict[str, Any]:
        """Apply suggested budget limits from refine_budgets_from_spending."""
        for cat, s in suggestions.items():
            await self.set_category_budget(user_id, cat, s["suggested_limit"])

        await self.budgets.update_one(
            {"user_id": user_id},
            {"$set": {"ai_refined": True, "last_refined_at": datetime.utcnow()}},
        )
        return await self.get_budget_profile(user_id)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _seed_defaults(self, user_id: str) -> Dict[str, Any]:
        """Insert default budget profile for a new user."""
        now = datetime.utcnow()
        doc = {
            "user_id": user_id,
            "monthly_budgets": {k: dict(v) for k, v in DEFAULT_BUDGETS.items()},
            "total_monthly_limit": None,
            "currency": "INR",
            "ai_refined": False,
            "last_refined_at": None,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.budgets.insert_one(doc)
        doc["_id"] = result.inserted_id
        return doc
