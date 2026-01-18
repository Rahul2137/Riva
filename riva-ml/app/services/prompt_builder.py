"""
Prompt Builder - Builds LLM prompts with user context and memory.
Injects user facts, preferences, session context into system prompts.
"""
from typing import Dict, List, Optional
from datetime import datetime


class PromptBuilder:
    """
    Builds context-aware prompts for LLM calls.
    Combines user memories, session context, and intent-specific instructions.
    """
    
    def __init__(self):
        self.base_system_prompt = """You are RIVA, a personal AI secretary. You help with:
- Tracking expenses and income
- Managing budgets
- Providing financial insights
- General assistance

Your personality:
- Friendly but professional
- Concise (2-3 sentences max)
- Supportive, never judgmental about spending
- Proactive with helpful suggestions"""
    
    def build_system_prompt(
        self,
        memory_context: Dict = None,
        session_context: Dict = None,
        intent: str = None
    ) -> str:
        """
        Build complete system prompt with all context.
        """
        prompt_parts = [self.base_system_prompt]
        
        # Add user memories
        if memory_context:
            memory_section = self._format_memory_context(memory_context)
            if memory_section:
                prompt_parts.append(f"\n\nUSER INFORMATION:\n{memory_section}")
        
        # Add session context
        if session_context:
            session_section = self._format_session_context(session_context)
            if session_section:
                prompt_parts.append(f"\n\nCURRENT CONTEXT:\n{session_section}")
        
        # Add intent-specific instructions
        if intent:
            intent_section = self._get_intent_instructions(intent)
            if intent_section:
                prompt_parts.append(f"\n\nCURRENT TASK:\n{intent_section}")
        
        return "\n".join(prompt_parts)
    
    def _format_memory_context(self, memory_context: Dict) -> str:
        """Format user memories for prompt."""
        sections = []
        
        # Facts about user
        if memory_context.get("facts"):
            facts = [f"- {f['key']}: {f['value']}" for f in memory_context["facts"]]
            sections.append(f"Known facts:\n" + "\n".join(facts))
        
        # User preferences
        if memory_context.get("preferences"):
            prefs = [f"- {p['key']}: {p['value']}" for p in memory_context["preferences"]]
            sections.append(f"Preferences:\n" + "\n".join(prefs))
        
        # Budget constraints
        if memory_context.get("constraints"):
            constraints = [f"- {c['key']}: {c['value']}" for c in memory_context["constraints"]]
            sections.append(f"Constraints:\n" + "\n".join(constraints))
        
        # Habits (with confidence)
        if memory_context.get("habits"):
            habits = [f"- {h['key']}: {h['value']} (confidence: {h.get('confidence', 1.0):.0%})" 
                     for h in memory_context["habits"]]
            sections.append(f"Observed habits:\n" + "\n".join(habits))
        
        return "\n\n".join(sections)
    
    def _format_session_context(self, session_context: Dict) -> str:
        """Format session context for prompt."""
        sections = []
        
        if session_context.get("last_topic"):
            sections.append(f"Last discussed topic: {session_context['last_topic']}")
        
        if session_context.get("last_category"):
            sections.append(f"Last expense category: {session_context['last_category']}")
        
        if session_context.get("pending_question"):
            sections.append(f"Waiting for: {session_context['pending_question']}")
            if session_context.get("pending_data"):
                sections.append(f"Pending data: {session_context['pending_data']}")
        
        # Recent conversation
        if session_context.get("recent_messages"):
            messages = session_context["recent_messages"][-3:]
            if messages:
                conv = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
                sections.append(f"Recent conversation:\n{conv}")
        
        return "\n".join(sections)
    
    def _get_intent_instructions(self, intent: str) -> str:
        """Get intent-specific instructions."""
        instructions = {
            "add_expense": """Handle expense tracking:
- Confirm the expense details
- If missing amount or category, ask politely
- Use defaults where reasonable
- Mention budget status if relevant""",
            
            "add_income": """Handle income logging:
- Confirm the income details
- Ask about recurring if salary
- Be encouraging about earnings""",
            
            "set_budget": """Handle budget setting:
- Confirm the budget amount and category
- Mention you'll track spending against it
- Be helpful about reasonable limits""",
            
            "get_insights": """Provide financial insights:
- Summarize spending patterns
- Compare to previous periods
- Give actionable suggestions
- Be supportive, never judgmental""",
            
            "correction": """Handle corrections:
- Understand what needs to be changed
- Confirm the update
- Be helpful and non-judgmental about mistakes""",
            
            "dont_track": """User doesn't want to track this:
- Acknowledge politely
- Don't ask follow-up questions about it
- Move on naturally"""
        }
        
        return instructions.get(intent, "")
    
    def build_expense_confirmation(
        self,
        amount: float,
        category: str,
        date: str = None
    ) -> str:
        """Build response for expense confirmation."""
        date_str = date or "today"
        return f"Got it. I've added ₹{amount:,.0f} under {category.title()} for {date_str}."
    
    def build_followup_question(
        self,
        missing_field: str,
        pending_data: Dict = None
    ) -> str:
        """Build followup question for missing information."""
        questions = {
            "amount": "How much was it?",
            "category": "What was this expense for?",
            "date": "When was this?"
        }
        
        base_question = questions.get(missing_field, f"What was the {missing_field}?")
        
        if pending_data and pending_data.get("amount"):
            return f"Sure — {base_question.lower()}"
        
        return base_question
    
    def build_budget_alert(
        self,
        category: str,
        percentage: float,
        amount_spent: float,
        budget_limit: float
    ) -> str:
        """Build budget alert message."""
        if percentage >= 1.0:
            return f"Heads up — you've exceeded your {category} budget. Spent ₹{amount_spent:,.0f} of ₹{budget_limit:,.0f}."
        elif percentage >= 0.9:
            return f"Heads up — you've used {percentage:.0%} of your {category} budget for this month."
        elif percentage >= 0.75:
            return f"FYI, you've used {percentage:.0%} of your {category} budget."
        return ""
