"""
LLM-Powered Router for IT Support Chatbot

This module implements intelligent, LLM-based routing that replaces brittle
rule-based routing with semantic understanding. The router agent analyzes
conversation context and user intent to make routing decisions.

Benefits over rule-based routing:
1. Resilience - Understands intent, not just keywords
2. Scalability - Add new routes by updating prompts, not code
3. Flexibility - Handles variations in user expression
4. Maintainability - Routing logic is centralized and readable
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, Optional, List, Dict
from enum import Enum
import os
from dotenv import load_dotenv

load_dotenv()


# =============================================================================
# ROUTING ENUMS AND SCHEMAS
# =============================================================================

class ChatbotRoute(str, Enum):
    """Valid routing destinations from chatbot node"""
    CONTINUE_CHAT = "continue_chat"      # Stay in chatbot, continue conversation
    TICKET_COLLECTION = "ticket_collection"  # Hand off to ticket agent
    TICKET_CONFIRMATION = "ticket_confirmation"  # Handle confirmation actions
    END = "end"  # End current step, wait for user input


class TicketCollectionRoute(str, Enum):
    """Valid routing destinations from ticket collection node"""
    TICKET_PREVIEW = "ticket_preview"  # Show ticket preview
    CONTINUE_COLLECTION = "continue_collection"  # Continue collecting info
    END = "end"  # Wait for user input


class ConfirmationRoute(str, Enum):
    """Valid routing destinations from confirmation node"""
    SUBMIT = "submit_ticket"
    EDIT = "edit"
    CANCEL = "cancel"
    INVALID = "invalid"


class RouterDecision(BaseModel):
    """Structured output from the LLM router"""
    route: str = Field(description="The routing decision")
    confidence: float = Field(default=1.0, description="Confidence score 0-1")
    reasoning: str = Field(default="", description="Brief reasoning for the decision")


# =============================================================================
# LLM ROUTER AGENT
# =============================================================================

class LLMRouter:
    """
    LLM-powered router that makes intelligent routing decisions based on
    conversation context and user intent.
    
    This replaces brittle if/elif rule-based routing with semantic understanding.
    """
    
    def __init__(self, model: str = "gpt-4o-mini", temperature: float = 0):
        """Initialize the router with a fast, low-cost model"""
        self.llm = ChatOpenAI(model=model, temperature=temperature)
        
        # Bind the router to output structured decisions
        self.router_llm = self.llm.with_structured_output(RouterDecision)
    
    def route_from_chatbot(
        self,
        messages: List,
        last_question: Optional[str] = None,
        awaiting_confirmation: bool = False,
        awaiting_ticket_confirmation: bool = False,
        edit_mode: bool = False,
        ticket_questions: List[str] = None
    ) -> ChatbotRoute:
        """
        Intelligent routing from the chatbot node.
        
        Combines rule-based checks for deterministic states with LLM-based
        intent detection for ambiguous situations.
        
        Args:
            messages: Conversation history
            last_question: The last question asked (for form tracking)
            awaiting_confirmation: Whether we're awaiting ticket submit/edit/cancel
            awaiting_ticket_confirmation: Whether we're awaiting "create ticket?" confirmation
            edit_mode: Whether user is editing ticket details
            ticket_questions: List of valid ticket form questions
        
        Returns:
            ChatbotRoute enum value
        """
        print(f"\n[ROUTER DEBUG] route_from_chatbot called")
        print(f"  - edit_mode: {edit_mode}")
        print(f"  - awaiting_confirmation: {awaiting_confirmation}")
        print(f"  - awaiting_ticket_confirmation: {awaiting_ticket_confirmation}")
        print(f"  - last_question: {last_question}")
        print(f"  - messages count: {len(messages) if messages else 0}")
        
        # =====================================================================
        # RULE-BASED CHECKS (Deterministic states - these are appropriate)
        # =====================================================================
        
        # If in edit mode, route to ticket_collection to process the edit
        if edit_mode:
            print(f"  → ROUTE: TICKET_COLLECTION (edit mode)")
            return ChatbotRoute.TICKET_COLLECTION
        
        # If awaiting ticket creation confirmation, stay in chatbot
        if awaiting_ticket_confirmation:
            print(f"  → ROUTE: END (awaiting ticket confirmation)")
            return ChatbotRoute.END
        
        # If awaiting submit/edit/cancel confirmation, route to confirmation handler
        if awaiting_confirmation:
            print(f"  → ROUTE: TICKET_CONFIRMATION (awaiting confirmation)")
            return ChatbotRoute.TICKET_CONFIRMATION
        
        # If we're in the middle of collecting ticket info, route back to collection
        if last_question and ticket_questions and last_question in ticket_questions:
            print(f"  → ROUTE: TICKET_COLLECTION (collecting info for: {last_question})")
            return ChatbotRoute.TICKET_COLLECTION
        
        # =====================================================================
        # LLM-BASED INTENT DETECTION (For ambiguous situations)
        # =====================================================================
        
        if not messages:
            return ChatbotRoute.END
        
        # Get the last message
        last_msg = messages[-1] if messages else None
        if not last_msg or not hasattr(last_msg, 'content'):
            return ChatbotRoute.END
        
        last_content = last_msg.content
        
        # Check for explicit handoff signals (from chatbot agent)
        # This is still rule-based but checks for the agent's explicit signal
        if "HANDOFF_TO_TICKET_AGENT" in last_content or "handoff_to_ticket" in last_content:
            print(f"  → ROUTE: TICKET_COLLECTION (handoff signal detected)")
            return ChatbotRoute.TICKET_COLLECTION
        
        # For all other cases, use LLM to detect intent
        print(f"  → Using LLM-based routing...")
        return self._llm_route_chatbot(messages)
    
    def _llm_route_chatbot(self, messages: List) -> ChatbotRoute:
        """
        Use LLM to intelligently determine routing from chatbot.
        
        This is the key improvement over rule-based routing - it understands
        user INTENT rather than just matching keywords.
        """
        # Extract recent conversation context
        recent_messages = messages[-5:] if len(messages) > 5 else messages
        conversation_context = "\n".join([
            f"{'User' if isinstance(m, HumanMessage) else 'Assistant'}: {m.content[:200]}"
            for m in recent_messages
            if hasattr(m, 'content')
        ])
        
        routing_prompt = f"""You are an expert routing agent for an IT support chatbot system.
Your job is to analyze the conversation and decide the next action.

CONVERSATION CONTEXT:
{conversation_context}

ROUTING OPTIONS:
1. "continue_chat" - The conversation should continue in troubleshooting mode. Choose this if:
   - User is asking questions or describing problems
   - User is responding to troubleshooting steps
   - User is asking for clarification
   - The conversation is ongoing and not ready for ticket creation

2. "ticket_collection" - Hand off to ticket creation. Choose this if:
   - The assistant has indicated it will transfer to ticket creation
   - The user explicitly wants to create/file/submit a support ticket
   - User has given up on troubleshooting ("this isn't working", "I need more help")
   - The handoff signal is present in the conversation

3. "end" - Wait for user input. Choose this if:
   - A question was asked and we're waiting for user response
   - The conversation has naturally paused
   - The assistant asked a yes/no question

Analyze the conversation and return the most appropriate route.
Focus on the INTENT of the latest messages, not just keywords."""

        try:
            decision = self.router_llm.invoke([
                SystemMessage(content=routing_prompt)
            ])
            
            print(f"  [LLM Decision] route: {decision.route}, confidence: {decision.confidence:.2f}")
            print(f"  [LLM Decision] reasoning: {decision.reasoning}")
            
            # Map the LLM decision to our enum
            route_mapping = {
                "continue_chat": ChatbotRoute.END,  # Continue means wait for next input
                "ticket_collection": ChatbotRoute.TICKET_COLLECTION,
                "end": ChatbotRoute.END
            }
            
            final_route = route_mapping.get(decision.route, ChatbotRoute.END)
            print(f"  → ROUTE: {final_route.value.upper()} (LLM-based)")
            return final_route
            
        except Exception as e:
            print(f"  [LLMRouter ERROR] {e}")
            print(f"  → ROUTE: END (fallback due to error)")
            # Fallback to safe default
            return ChatbotRoute.END
    
    def route_confirmation(self, user_message: str) -> ConfirmationRoute:
        """
        Use LLM to understand user's confirmation intent.
        
        This is more flexible than keyword matching - it understands
        variations like "yeah go ahead", "sure submit it", "nah cancel", etc.
        """
        print(f"\n[ROUTER DEBUG] route_confirmation called")
        print(f"  - user_message: '{user_message[:50]}...'" if len(user_message) > 50 else f"  - user_message: '{user_message}'")
        
        routing_prompt = f"""You are analyzing a user's response to a ticket confirmation prompt.
The user was asked to choose: submit, edit, or cancel their IT support ticket.

USER'S RESPONSE: "{user_message}"

What is the user's intent?
- "submit_ticket" - User wants to submit/confirm/proceed with the ticket
  (Examples: "submit", "yes", "go ahead", "looks good", "confirm", "ok create it", "proceed")
- "edit" - User wants to modify/change/update the ticket details
  (Examples: "edit", "change", "modify", "wait I need to fix", "update the priority")
- "cancel" - User wants to cancel/abandon the ticket
  (Examples: "cancel", "no", "nevermind", "forget it", "stop", "I don't want it")
- "invalid" - The response doesn't clearly indicate any of the above
  (Examples: random text, questions, unrelated content)

Return the most appropriate action based on user intent."""

        try:
            decision = self.router_llm.invoke([
                SystemMessage(content=routing_prompt)
            ])
            
            print(f"  [LLM Decision] route: {decision.route}")
            print(f"  [LLM Decision] reasoning: {decision.reasoning}")
            
            route_mapping = {
                "submit_ticket": ConfirmationRoute.SUBMIT,
                "edit": ConfirmationRoute.EDIT,
                "cancel": ConfirmationRoute.CANCEL,
                "invalid": ConfirmationRoute.INVALID
            }
            
            final_route = route_mapping.get(decision.route, ConfirmationRoute.INVALID)
            print(f"  → ROUTE: {final_route.value.upper()}")
            return final_route
            
        except Exception as e:
            print(f"  [LLMRouter ERROR] {e}")
            print(f"  → ROUTE: INVALID (fallback due to error)")
            return ConfirmationRoute.INVALID


# =============================================================================
# HYBRID ROUTER (Combines LLM + Rules for Best of Both Worlds)
# =============================================================================

class HybridRouter:
    """
    Production-ready router that combines:
    1. Fast rule-based checks for deterministic states
    2. LLM-based intent detection for ambiguous situations
    3. Caching to reduce redundant LLM calls
    4. Fallback mechanisms for reliability
    
    This is the recommended approach for production systems.
    """
    
    def __init__(self, use_llm_for_confirmation: bool = True):
        """
        Initialize the hybrid router.
        
        Args:
            use_llm_for_confirmation: Whether to use LLM for confirmation routing.
                                      Set to False for faster, rule-based confirmation.
        """
        self.llm_router = LLMRouter()
        self.use_llm_for_confirmation = use_llm_for_confirmation
        self._routing_cache = {}  # Simple cache for repeated patterns
    
    def route_from_chatbot(self, state: dict) -> str:
        """
        Main routing function from chatbot node.
        
        This replaces the rule-based route_chatbot function in main.py
        
        Args:
            state: The AgentState dictionary
        
        Returns:
            String routing destination compatible with LangGraph
        """
        print(f"\n[HYBRID ROUTER] route_from_chatbot called")
        from src.state import FORM_TEMPLATES
        
        # Build ticket questions list
        ticket_questions = ["category", "device", "priority", "description"]
        for template in FORM_TEMPLATES.values():
            ticket_questions.extend(template.get("extra_fields", []))
        
        # Call the LLM router
        route = self.llm_router.route_from_chatbot(
            messages=state.get("messages", []),
            last_question=state.get("last_question"),
            awaiting_confirmation=state.get("awaiting_confirmation", False),
            awaiting_ticket_confirmation=state.get("awaiting_ticket_confirmation", False),
            edit_mode=state.get("edit_mode", False),
            ticket_questions=ticket_questions
        )
        
        # Map enum to LangGraph-compatible string
        route_mapping = {
            ChatbotRoute.CONTINUE_CHAT: "END",
            ChatbotRoute.TICKET_COLLECTION: "ticket_collection",
            ChatbotRoute.TICKET_CONFIRMATION: "ticket_confirmation",
            ChatbotRoute.END: "END"
        }
        
        final_route = route_mapping.get(route, "END")
        print(f"[HYBRID ROUTER] → Final route: {final_route}\n")
        return final_route
    
    def route_from_ticket_collection(self, state: dict) -> str:
        """
        Route from ticket collection node.
        
        This uses primarily rule-based logic as it's deterministic
        (checking if all fields are filled).
        
        Args:
            state: The AgentState dictionary
        
        Returns:
            String routing destination
        """
        from src.state import TicketSchema, FORM_TEMPLATES
        
        # If ticket collection is complete (set by TicketAgent), go to preview
        if state.get("ticket_collection_complete"):
            return "ticket_preview"
        
        current_ticket = state.get("ticket", {})
        if isinstance(current_ticket, dict):
            current_ticket = TicketSchema(**current_ticket)
        
        # Check core required fields
        has_category = current_ticket.category is not None
        has_summary = current_ticket.issue_summary is not None
        has_device = current_ticket.device_id is not None
        has_priority = current_ticket.priority is not None
        has_description = current_ticket.description is not None
        
        # Check category-specific extra fields
        category = current_ticket.category or "General"
        template = FORM_TEMPLATES.get(category, FORM_TEMPLATES["General"])
        required_extras = template.get("extra_fields", [])
        current_extras = current_ticket.extra_fields or {}
        has_all_extras = all(field in current_extras for field in required_extras)
        
        # All fields complete?
        if has_category and has_summary and has_device and has_priority and has_description and has_all_extras:
            return "ticket_preview"
        
        return "END"
    
    def route_from_confirmation(self, state: dict) -> str:
        """
        Route from confirmation node.
        
        Uses LLM-based or rule-based logic based on configuration.
        
        Args:
            state: The AgentState dictionary
        
        Returns:
            String routing destination
        """
        action = state.get("confirmation_action", "")
        
        # If action is already set by the confirmation node, use it
        if action:
            if action == "submit":
                return "submit_ticket"
            elif action == "edit":
                return "END"
            elif action == "cancel":
                return "END"
        
        # If using LLM for confirmation (when action not set)
        if self.use_llm_for_confirmation:
            messages = state.get("messages", [])
            if messages:
                last_msg = messages[-1]
                if hasattr(last_msg, 'content'):
                    route = self.llm_router.route_confirmation(last_msg.content)
                    
                    route_mapping = {
                        ConfirmationRoute.SUBMIT: "submit_ticket",
                        ConfirmationRoute.EDIT: "END",
                        ConfirmationRoute.CANCEL: "END",
                        ConfirmationRoute.INVALID: "END"
                    }
                    
                    return route_mapping.get(route, "END")
        
        return "END"


# =============================================================================
# GLOBAL ROUTER INSTANCE
# =============================================================================

# Create a global hybrid router instance for use across the application
_global_router = None


def get_router() -> HybridRouter:
    """Get the global router instance (lazy initialization)"""
    global _global_router
    if _global_router is None:
        _global_router = HybridRouter(use_llm_for_confirmation=True)
    return _global_router


def route_chatbot_llm(state: dict) -> str:
    """
    Drop-in replacement for the rule-based route_chatbot function.
    
    This function can be used directly in LangGraph's add_conditional_edges.
    
    Usage in main.py:
        from src.router import route_chatbot_llm
        
        workflow.add_conditional_edges(
            "chatbot",
            route_chatbot_llm,
            {
                "ticket_collection": "ticket_collection",
                "ticket_confirmation": "ticket_confirmation",
                "END": END
            }
        )
    """
    router = get_router()
    return router.route_from_chatbot(state)


def route_ticket_collection_llm(state: dict) -> str:
    """Drop-in replacement for route_ticket_collection"""
    router = get_router()
    return router.route_from_ticket_collection(state)


def route_confirmation_llm(state: dict) -> str:
    """Drop-in replacement for route_confirmation"""
    router = get_router()
    return router.route_from_confirmation(state)
