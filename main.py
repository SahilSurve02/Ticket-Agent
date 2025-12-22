from langgraph.graph import StateGraph, END, START
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket
from src.nodes import chatbot_node, ticket_collection_node, ticket_confirmation_node, ticket_preview_node, submit_ticket_node
from src.kb import initialize_kb_with_check
from langgraph.checkpoint.memory import MemorySaver
import uuid
import os
from dotenv import load_dotenv
load_dotenv()

# =============================================================================
# ROUTING CONFIGURATION
# =============================================================================
# Set to True to use LLM-based intelligent routing
# Set to False to use rule-based routing (faster, but less flexible)
USE_LLM_ROUTING = os.getenv("USE_LLM_ROUTING", "false").lower() == "true"

# Import LLM router if enabled
if USE_LLM_ROUTING:
    try:
        from src.router import route_chatbot_llm, route_ticket_collection_llm, route_confirmation_llm
        print("[ROUTING] Using LLM-based intelligent routing")
    except ImportError as e:
        print(f"[ROUTING] LLM router not available, falling back to rule-based: {e}")
        USE_LLM_ROUTING = False

if not USE_LLM_ROUTING:
    print("[ROUTING] Using rule-based routing")


# =============================================================================
# RULE-BASED ROUTING LOGIC (Default - Fast and Reliable)
# =============================================================================

def route_chatbot_rules(state: AgentState):
    """
    Routes from chatbot based on state - Rule-based implementation
    
    INDUSTRY-STANDARD: Uses structured escalate_to_ticket flag for 
    deterministic handoff (replaces fragile string matching)
    """
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
            # Check for agent handoff signal
            if "HANDOFF_TO_TICKET_AGENT" in last_msg.content:
                return "ticket_collection"
            # Legacy handoff (for backwards compatibility)
            if "handoff_to_ticket" in last_msg.content:
                return "ticket_collection"
    
    return END


def route_ticket_collection_rules(state: AgentState):
    """Routes from ticket collection - Rule-based implementation"""
    
    # If ticket collection is complete (set by TicketAgent after edit), go to preview
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
    
    return END  # Wait for user response


def route_confirmation_rules(state: AgentState):
    """Routes from confirmation based on user's choice - Rule-based implementation"""
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


# =============================================================================
# ROUTER SELECTION - Choose between LLM-based and Rule-based
# =============================================================================

def route_chatbot(state: AgentState):
    """Main chatbot router - uses LLM or rules based on configuration"""
    if USE_LLM_ROUTING:
        result = route_chatbot_llm(state)
        # Convert string result to END if needed
        return END if result == "END" else result
    return route_chatbot_rules(state)


def route_ticket_collection(state: AgentState):
    """Main ticket collection router - uses LLM or rules based on configuration"""
    if USE_LLM_ROUTING:
        result = route_ticket_collection_llm(state)
        return END if result == "END" else result
    return route_ticket_collection_rules(state)


def route_confirmation(state: AgentState):
    """Main confirmation router - uses LLM or rules based on configuration"""
    if USE_LLM_ROUTING:
        result = route_confirmation_llm(state)
        return END if result == "END" else result
    return route_confirmation_rules(state)


# =============================================================================
# BUILD WORKFLOW GRAPH
# =============================================================================

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


# =============================================================================
# MAIN CHAT FUNCTION
# =============================================================================

def run_chat():
    """Main chat loop"""
    # Initialize KB
    from src.kb import set_global_kb
    kb = initialize_kb_with_check("./chroma_db")
    set_global_kb(kb)
    
    if kb:
        print("✓ Knowledge base initialized successfully")
    else:
        print("⚠ Warning: Running without knowledge base")
    
    # Simulated user info (would come from login session in production)
    user_info = {
        "user_id": "EMP-12345",
        "user_name": "Krishna Ronaldo",
        "email": "krishna.ronaldo@company.com",
        "phone": "+1-777-0123",
        "department": "Engineering"
    }
    
    # Initial state
    initial_input = {
        "user_info": user_info,
        "user_devices": ["Dell Latitude 5420", "iPad Pro", "iPhone 14", "MacBook Pro", "HP Printer LaserJet 200"],
        "ticket": create_empty_ticket(),
        "ticket_preview_shown": False,
        "awaiting_confirmation": False,
        "last_question": None,
        "current_extra_field_index": 0,
        "detected_category": None
    }
    
    # Setup
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    print("\n" + "="*60)
    print("IT SUPPORT CHATBOT")
    print("="*60)
    print(f"Logged in as: {user_info['user_name']} ({user_info['email']})")
    print("Type 'q' to quit")
    print("="*60 + "\n")
    
    first_turn = True
    
    while True:
        user_text = input("You: ").strip()
        
        if user_text.lower() in ["q", "quit", "exit"]:
            print("\nGoodbye!")
            break
        
        if not user_text:
            continue
        
        # Build input
        input_message = {"messages": [HumanMessage(content=user_text)]}
        
        # First turn: include initial state
        if first_turn:
            input_message.update(initial_input)
            first_turn = False
        
        # Process through graph
        try:
            for event in app.stream(input_message, config=config):
                for node_name, state_update in event.items():
                    if not state_update:
                        continue
                    
                    if "messages" in state_update and state_update["messages"]:
                        last_msg = state_update["messages"][-1]
                        # Don't print agent handoff signals to user
                        content = last_msg.content
                        if "HANDOFF_TO_TICKET_AGENT" not in content and "handoff_to_ticket" not in content:
                            print(f"\nBot: {content}")
        
        except Exception as e:
            print(f"\n[Error]: {e}")
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    run_chat()
