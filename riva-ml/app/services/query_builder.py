"""
Query Builder - Converts GPT query_spec into validated MongoDB queries.
Provides security by validating all inputs before building queries.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List


# Allowed values for validation
ALLOWED_TYPES = ["expense", "income", "all"]
ALLOWED_CATEGORIES = ["food", "transport", "shopping", "entertainment", "bills", "health", "personal", "other", "income", None]
ALLOWED_DATE_RANGES = ["today", "yesterday", "this_week", "last_week", "this_month", "last_month", "last_30_days", "last_90_days", "all_time"]
ALLOWED_GROUP_BY = ["category", "date", "day", "week", "month", None]
ALLOWED_SORT_BY = ["amount", "date", "created_at", None]


class QueryBuilder:
    """
    Builds validated MongoDB queries from GPT-generated query_spec.
    
    Example query_spec:
    {
        "type": "expense",
        "category": "food",
        "date_range": "last_week",
        "min_amount": 500,
        "max_amount": null,
        "group_by": "category",
        "sort_by": "amount",
        "sort_order": "desc",
        "limit": 10
    }
    """
    
    def __init__(self, user_id: str):
        self.user_id = user_id
    
    def build_query(self, query_spec: Dict) -> Dict:
        """
        Build MongoDB query from query_spec.
        Returns validated query dict.
        """
        query = {"user_id": self.user_id}
        
        # Transaction type filter
        tx_type = query_spec.get("type", "expense")
        if tx_type in ALLOWED_TYPES and tx_type != "all":
            query["type"] = tx_type
        
        # Category filter
        category = query_spec.get("category")
        if category and category in ALLOWED_CATEGORIES:
            query["category"] = category
        
        # Date range filter
        date_range = query_spec.get("date_range", "this_month")
        if date_range in ALLOWED_DATE_RANGES:
            date_filter = self._get_date_filter(date_range)
            if date_filter:
                query["$or"] = [
                    {"created_at": date_filter},
                    {"date": {"$gte": date_filter["$gte"].strftime("%Y-%m-%d")}}
                ]
        
        # Amount filters
        min_amount = query_spec.get("min_amount")
        max_amount = query_spec.get("max_amount")
        if min_amount is not None or max_amount is not None:
            amount_filter = {}
            if min_amount is not None:
                try:
                    amount_filter["$gte"] = float(min_amount)
                except (ValueError, TypeError):
                    pass
            if max_amount is not None:
                try:
                    amount_filter["$lte"] = float(max_amount)
                except (ValueError, TypeError):
                    pass
            if amount_filter:
                query["amount"] = amount_filter
        
        return query
    
    def build_aggregation(self, query_spec: Dict) -> Optional[List[Dict]]:
        """
        Build MongoDB aggregation pipeline if grouping/aggregation needed.
        """
        group_by = query_spec.get("group_by")
        if not group_by or group_by not in ALLOWED_GROUP_BY:
            return None
        
        # Build match stage from query
        query = self.build_query(query_spec)
        pipeline = [{"$match": query}]
        
        # Group stage
        if group_by == "category":
            pipeline.append({
                "$group": {
                    "_id": "$category",
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1}
                }
            })
        elif group_by in ["date", "day"]:
            pipeline.append({
                "$group": {
                    "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}},
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1}
                }
            })
        elif group_by == "week":
            pipeline.append({
                "$group": {
                    "_id": {"$isoWeek": "$created_at"},
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1}
                }
            })
        elif group_by == "month":
            pipeline.append({
                "$group": {
                    "_id": {"$month": "$created_at"},
                    "total": {"$sum": "$amount"},
                    "count": {"$sum": 1}
                }
            })
        
        # Sort stage
        sort_by = query_spec.get("sort_by")
        sort_order = -1 if query_spec.get("sort_order") == "desc" else 1
        if sort_by == "amount":
            pipeline.append({"$sort": {"total": sort_order}})
        elif sort_by in ["date", "created_at"]:
            pipeline.append({"$sort": {"_id": sort_order}})
        else:
            pipeline.append({"$sort": {"total": -1}})  # Default: highest first
        
        # Limit
        limit = query_spec.get("limit")
        if limit and isinstance(limit, int) and 1 <= limit <= 100:
            pipeline.append({"$limit": limit})
        
        return pipeline
    
    def _get_date_filter(self, date_range: str) -> Optional[Dict]:
        """Convert date range string to MongoDB date filter."""
        now = datetime.now()
        
        if date_range == "today":
            start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "yesterday":
            start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "this_week":
            start = now - timedelta(days=now.weekday())
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "last_week":
            start = now - timedelta(days=now.weekday() + 7)
            start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "this_month":
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "last_month":
            first_of_month = now.replace(day=1)
            start = (first_of_month - timedelta(days=1)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        elif date_range == "last_30_days":
            start = now - timedelta(days=30)
        elif date_range == "last_90_days":
            start = now - timedelta(days=90)
        elif date_range == "all_time":
            return None
        else:
            start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)  # Default to this month
        
        return {"$gte": start}
    
    def get_date_label(self, date_range: str) -> str:
        """Get human-readable label for date range."""
        labels = {
            "today": "today",
            "yesterday": "yesterday",
            "this_week": "this week",
            "last_week": "last week",
            "this_month": "this month",
            "last_month": "last month",
            "last_30_days": "in the last 30 days",
            "last_90_days": "in the last 90 days",
            "all_time": "all time"
        }
        return labels.get(date_range, "this month")
