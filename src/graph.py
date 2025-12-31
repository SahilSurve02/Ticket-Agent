"""
Unified LangGraph Workflow Builder

This module centralizes all graph-related logic including:
- Routing functions (rule-based and LLM-based)
- Workflow graph construction
- Configuration management

Both main.py (CLI) and app.py (Streamlit UI) use this module
to avoid code duplication and ensure consistent behavior.
"""

import os
import logging
from typing import Optional, Dict, Any, List
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage, AIMessage
from dotenv import load_dotenv

from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket
from src.nodes import (
    chatbot_node, 
    ticket_collection_node, 
    ticket_confirmation_node, 
    ticket_preview_node, 
    submit_ticket_node
)

load_dotenv()

# =============================================================================
# LOGGING CONFIGURATION
# =============================================================================
logger = logging.getLogger(__name__)
_logging_configured = False  # Flag to prevent duplicate setup


# =============================================================================
# ROUTING CONFIGURATION
# =============================================================================
def get_use_llm_routing() -> bool:
    """
    Get LLM routing configuration from environment.
    
    Returns:
        bool: True if LLM-based routing is enabled, False for rule-based routing.
    """
    return os.getenv("USE_LLM_ROUTING", "false").lower() == "true"


# LLM router functions (imported lazily to avoid import errors if not used)
_llm_routers_loaded = False
_route_chatbot_llm = None
_route_ticket_collection_llm = None
_route_confirmation_llm = None


def _load_llm_routers() -> bool:
    """
    Lazily load LLM router functions.
    
    Returns:
        bool: True if LLM routers loaded successfully, False otherwise.
    """
    global _llm_routers_loaded, _route_chatbot_llm, _route_ticket_collection_llm, _route_confirmation_llm
    
    if _llm_routers_loaded:
        return _route_chatbot_llm is not None
    
    try:
        from src.router import route_chatbot_llm, route_ticket_collection_llm, route_confirmation_llm
        _route_chatbot_llm = route_chatbot_llm
        _route_ticket_collection_llm = route_ticket_collection_llm
        _route_confirmation_llm = route_confirmation_llm
        _llm_routers_loaded = True
        logger.info("[ROUTING] LLM-based routing loaded successfully")
        return True
    except ImportError as e:
        logger.warning(f"[ROUTING] LLM router not available, using rule-based: {e}")
        _llm_routers_loaded = True
        return False


# =============================================================================
# RULE-BASED ROUTING LOGIC (Default - Fast and Reliable)
# =============================================================================

def route_chatbot_rules(state: AgentState) -> str:
    """
    Routes from chatbot based on state - Rule-based implementation.
    
    INDUSTRY-STANDARD: Uses structured escalate_to_ticket flag for 
    deterministic handoff (replaces fragile string matching).
    
    Args:
        state: Current agent state dictionary.
        
    Returns:
        str: Next node name or END.
    """
    try:
        # STRUCTURED HANDOFF: Check flag FIRST (deterministic, reliable)
        if state.get("escalate_to_ticket") is True:
            return "ticket_collection"
       
        # If in edit mode, route to ticket_collection to process the edit
        if state.get("edit_mode"):
            return "ticket_collection"
        
        # If awaiting ticket creation confirmation, stay in chatbot to handle response
        if state.get("awaiting_ticket_confirmation"):
            return END  # Stay in chatbot, will process confirmation on next user input
        
        # If awaiting confirmation (preview shown), route to confirmation handler
        if state.get("awaiting_confirmation"):
            return "ticket_confirmation"
        
        # Get all possible question fields (base + all category extras)
        ticket_questions = ["category", "device", "priority", "description"]
        for template in FORM_TEMPLATES.values():
            ticket_questions.extend(template.get("extra_fields", []))
        
        # If we asked a ticket question, route to ticket_collection
        last_question = state.get("last_question")
        if last_question in ticket_questions:
            return "ticket_collection"
        
        # Legacy fallback: Check last message for agent handoff trigger
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, 'content'):
                content = last_msg.content
                # Check for agent handoff signal
                if "HANDOFF_TO_TICKET_AGENT" in content:
                    return "ticket_collection"
                # Legacy handoff (for backwards compatibility)
                if "handoff_to_ticket" in content:
                    return "ticket_collection"
        
        return END
        
    except Exception as e:
        logger.error(f"[ROUTING] Error in route_chatbot_rules: {e}", exc_info=True)
        return END  # Safe fallback


def route_ticket_collection_rules(state: AgentState) -> str:
    """
    Routes from ticket collection - Rule-based implementation.
    
    Args:
        state: Current agent state dictionary.
        
    Returns:
        str: Next node name or END.
    """
    try:
        # If ticket collection is complete (set by TicketAgent after edit), go to preview
        if state.get("ticket_collection_complete"):
            return "ticket_preview"
        
        current_ticket = state.get("ticket", {})
        if isinstance(current_ticket, dict):
            try:
                current_ticket = TicketSchema(**current_ticket)
            except Exception as e:
                logger.warning(f"[ROUTING] Failed to parse ticket schema: {e}")
                return END
        
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
        
        return END  # Wait for user response
        
    except Exception as e:
        logger.error(f"[ROUTING] Error in route_ticket_collection_rules: {e}", exc_info=True)
        return END


def route_confirmation_rules(state: AgentState) -> str:
    """
    Routes from confirmation based on user's choice - Rule-based implementation.
    
    Args:
        state: Current agent state dictionary.
        
    Returns:
        str: Next node name or END.
    """
    try:
        action = state.get("confirmation_action", "")
        
        if action == "submit":
            return "submit_ticket"
        elif action == "edit":
            # Don't immediately route to ticket_collection
            # Instead, END and wait for user's next message (the actual edit request)
            return END
        elif action == "cancel":
            return END  # Just end, state already reset
        else:
            return END  # Invalid response, wait for valid input
            
    except Exception as e:
        logger.error(f"[ROUTING] Error in route_confirmation_rules: {e}", exc_info=True)
        return END


# =============================================================================
# ROUTER SELECTION - Choose between LLM-based and Rule-based
# =============================================================================

def route_chatbot(state: AgentState) -> str:
    """
    Main chatbot router - uses LLM or rules based on configuration.
    
    Args:
        state: Current agent state dictionary.
        
    Returns:
        str: Next node name or END.
    """
    try:
        if get_use_llm_routing() and _load_llm_routers() and _route_chatbot_llm:
            result = _route_chatbot_llm(state)
            # Convert string result to END if needed
            return END if result == "END" else result
        return route_chatbot_rules(state)
    except Exception as e:
        logger.error(f"[ROUTING] Error in route_chatbot: {e}", exc_info=True)
        return END


def route_ticket_collection(state: AgentState) -> str:
    """
    Main ticket collection router - uses LLM or rules based on configuration.
    
    Args:
        state: Current agent state dictionary.
        
    Returns:
        str: Next node name or END.
    """
    try:
        if get_use_llm_routing() and _load_llm_routers() and _route_ticket_collection_llm:
            result = _route_ticket_collection_llm(state)
            return END if result == "END" else result
        return route_ticket_collection_rules(state)
    except Exception as e:
        logger.error(f"[ROUTING] Error in route_ticket_collection: {e}", exc_info=True)
        return END


def route_confirmation(state: AgentState) -> str:
    """
    Main confirmation router - uses LLM or rules based on configuration.
    
    Args:
        state: Current agent state dictionary.
        
    Returns:
        str: Next node name or END.
    """
    try:
        if get_use_llm_routing() and _load_llm_routers() and _route_confirmation_llm:
            result = _route_confirmation_llm(state)
            return END if result == "END" else result
        return route_confirmation_rules(state)
    except Exception as e:
        logger.error(f"[ROUTING] Error in route_confirmation: {e}", exc_info=True)
        return END


# =============================================================================
# WORKFLOW GRAPH BUILDER
# =============================================================================

def build_workflow() -> StateGraph:
    """
    Build and return the LangGraph workflow.
    
    This function creates the complete state machine graph with all nodes
    and conditional edges for the IT support chatbot.
    
    Returns:
        StateGraph: The configured workflow graph (not compiled).
        
    Raises:
        RuntimeError: If workflow construction fails.
    """
    try:
        workflow = StateGraph(AgentState)
        
        # Add all nodes
        workflow.add_node("chatbot", chatbot_node)
        workflow.add_node("ticket_collection", ticket_collection_node)
        workflow.add_node("ticket_preview", ticket_preview_node)
        workflow.add_node("ticket_confirmation", ticket_confirmation_node)
        workflow.add_node("submit_ticket", submit_ticket_node)
        
        # Set entry point
        workflow.set_entry_point("chatbot")
        
        # Add edges
        workflow.add_conditional_edges(
            "chatbot",
            route_chatbot,
            {
                "ticket_collection": "ticket_collection",
                "ticket_confirmation": "ticket_confirmation",
                END: END
            }
        )
        
        workflow.add_conditional_edges(
            "ticket_collection",
            route_ticket_collection,
            {
                "ticket_preview": "ticket_preview",
                END: END
            }
        )
        
        workflow.add_edge("ticket_preview", END)
        
        workflow.add_conditional_edges(
            "ticket_confirmation",
            route_confirmation,
            {
                "submit_ticket": "submit_ticket",
                "ticket_collection": "ticket_collection",
                END: END
            }
        )
        
        workflow.add_edge("submit_ticket", END)
        
        logger.info("[WORKFLOW] Graph built successfully")
        return workflow
        
    except Exception as e:
        logger.error(f"[WORKFLOW] Failed to build workflow: {e}", exc_info=True)
        raise RuntimeError(f"Failed to build workflow graph: {e}") from e


def compile_workflow(workflow: StateGraph, checkpointer: Optional[MemorySaver] = None):
    """
    Compile the workflow graph with optional checkpointer.
    
    Args:
        workflow: The StateGraph to compile.
        checkpointer: Optional MemorySaver for state persistence.
        
    Returns:
        Compiled workflow application.
        
    Raises:
        RuntimeError: If compilation fails.
    """
    try:
        if checkpointer:
            app = workflow.compile(checkpointer=checkpointer)
        else:
            app = workflow.compile()
        
        logger.info("[WORKFLOW] Graph compiled successfully")
        return app
        
    except Exception as e:
        logger.error(f"[WORKFLOW] Failed to compile workflow: {e}", exc_info=True)
        raise RuntimeError(f"Failed to compile workflow: {e}") from e


def create_initial_state(
    user_info: Dict[str, str],
    user_devices: List[str]
) -> Dict[str, Any]:
    """
    Create the initial agent state for a new conversation.
    
    Args:
        user_info: User information dictionary with keys:
            - user_id, user_name, email, phone, department
        user_devices: List of user's registered devices.
        
    Returns:
        Dict containing the initial agent state.
    """
    return {
        "user_info": user_info,
        "user_devices": user_devices,
        "ticket": create_empty_ticket(),
        "ticket_preview_shown": False,
        "awaiting_confirmation": False,
        "last_question": None,
        "current_extra_field_index": 0,
        "detected_category": None,
        "escalate_to_ticket": False,
        "edit_mode": False,
        "ticket_collection_complete": False,
        "awaiting_ticket_confirmation": False,
    }


# =============================================================================
# LOGGING SETUP HELPER
# =============================================================================

def setup_logging(level: int = logging.INFO, log_file: str = "Logs/app.log") -> None:
    """
    Configure logging for the workflow module with colorful console output.
    
    Args:
        level: Logging level (default: INFO).
        log_file: Path to log file (default: Logs/app.log).
    """
    global _logging_configured
    
    # Prevent duplicate configuration
    if _logging_configured:
        return
    
    import os
    try:
        from colorlog import ColoredFormatter
        use_colors = True
    except ImportError:
        use_colors = False
    
    # Ensure Logs directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)
    
    # Configure root logger with both file and console handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates
    root_logger.handlers.clear()
    
    # Create plain formatter for file logging
    file_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # File handler - logs everything to file without colors
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(level)
    file_handler.setFormatter(file_formatter)
    root_logger.addHandler(file_handler)
    
    # Console handler - logs to stdout with colors
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    
    if use_colors:
        # Colorful formatter for console
        color_formatter = ColoredFormatter(
            '%(log_color)s%(asctime)s%(reset)s - %(cyan)s%(name)s%(reset)s - %(log_color)s%(levelname)s%(reset)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            log_colors={
                'DEBUG': 'white',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red',
            },
            secondary_log_colors={},
            style='%'
        )
        console_handler.setFormatter(color_formatter)
    else:
        console_handler.setFormatter(file_formatter)
    
    root_logger.addHandler(console_handler)
    
    # Also set level for this module's logger
    logger.setLevel(level)
    
    # Disable propagation for child loggers to prevent duplicates
    for log_name in ['src.nodes', 'src.agents', 'src.kb', 'src.router', 'src.db']:
        child_logger = logging.getLogger(log_name)
        child_logger.propagate = True  # Allow propagation to root
        child_logger.handlers.clear()  # But clear any duplicate handlers
    
    _logging_configured = True
    logger.info(f"Logging initialized. Log file: {log_file}")
