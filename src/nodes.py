from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket, generate_ticket_id
from src.agents import get_chatbot_agent, get_ticket_agent
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# =============================================================================
# NODE 1: CHATBOT - Uses dedicated ChatbotAgent
# =============================================================================
def chatbot_node(state: AgentState):
    """
    Chatbot node - delegates to ChatbotAgent for troubleshooting
    """
    # Skip if in ticket mode
    last_question = state.get("last_question")
    awaiting_confirmation = state.get("awaiting_confirmation", False)
    
    ticket_questions = ["category", "device", "priority", "description"]
    for template in FORM_TEMPLATES.values():
        ticket_questions.extend(template.get("extra_fields", []))
    
    if last_question in ticket_questions or awaiting_confirmation:
        return {}
    
    # Delegate to ChatbotAgent
    agent = get_chatbot_agent()
    return agent.process(state)


# =============================================================================
# =============================================================================
# NODE 2: TICKET COLLECTION - Uses dedicated TicketAgent
# =============================================================================
def ticket_collection_node(state: AgentState):
    """
    Ticket collection node - delegates to TicketAgent for ticket management
    """
    # Delegate to TicketAgent
    agent = get_ticket_agent()
    return agent.process_ticket_collection(state)


# =============================================================================
# NODE 3: TICKET PREVIEW - Show formatted ticket preview
# =============================================================================
def ticket_preview_node(state: AgentState):
    """Show ticket preview and ask for confirmation"""
    current_ticket = state["ticket"]
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    user_info = state.get("user_info", {})
    category = current_ticket.category or "General"
    template = FORM_TEMPLATES.get(category, FORM_TEMPLATES["General"])
    
    # Build extra fields display
    extra_display = ""
    if current_ticket.extra_fields:
        for field_name, value in current_ticket.extra_fields.items():
            # Convert field_name to readable label
            label = field_name.replace("_", " ").title()
            extra_display += f"**{label}:** {value}\n"
    
    preview = f"""
📋 **Ticket Preview**

**--- User Information ---**
**Name:** {user_info.get('user_name', 'N/A')}
**Email:** {user_info.get('email', 'N/A')}
**Phone:** {user_info.get('phone', 'N/A')}
**Department:** {user_info.get('department', 'N/A')}

**--- Issue Details ---**
**Category:** {template['name']}
**Issue Summary:** {current_ticket.issue_summary or "Not provided"}
**Device:** {current_ticket.device_id or "Not provided"}
**Priority:** {current_ticket.priority or "Medium"}
{extra_display}
**Additional Notes:** {current_ticket.description or "None"}

---

Please review the information above.

**Options:**
• Type **"submit"** to create the ticket
• Type **"edit"** to make changes
• Type **"cancel"** to cancel

What would you like to do?
"""
    
    return {
        "messages": [AIMessage(content=preview)],
        "ticket_preview_shown": True,
        "awaiting_confirmation": True
    }


# =============================================================================
# NODE 4: TICKET CONFIRMATION - Handle submit/edit/cancel
# =============================================================================
def ticket_confirmation_node(state: AgentState):
    """Handle user's confirmation response"""
    messages = state["messages"]
    last_user_message = messages[-1].content.lower().strip()
    
    if any(word in last_user_message for word in ["submit", "yes", "confirm", "ok", "proceed", "create"]):
        return {
            "messages": [AIMessage(content="Creating your ticket...")],
            "confirmation_action": "submit",
            "awaiting_confirmation": False
        }
    
    elif any(word in last_user_message for word in ["edit", "change", "modify", "update"]):
        return {
            "messages": [AIMessage(content="What would you like to change? (e.g., 'change priority to high' or 'update description')")],
            "confirmation_action": "edit",
            "awaiting_confirmation": False
        }
    
    elif any(word in last_user_message for word in ["cancel", "no", "nevermind", "back", "stop"]):
        return {
            "messages": [AIMessage(content="Ticket cancelled. How else can I help you?")],
            "confirmation_action": "cancel",
            "ticket": create_empty_ticket(),
            "ticket_preview_shown": False,
            "awaiting_confirmation": False,
            "last_question": None,
            "current_extra_field_index": 0
        }
    
    else:
        return {
            "messages": [AIMessage(content="Please respond with: **submit**, **edit**, or **cancel**")],
            "confirmation_action": "",
            "awaiting_confirmation": True
        }


# =============================================================================
# NODE 5: SUBMIT TICKET - Create the final ticket
# =============================================================================
def submit_ticket_node(state: AgentState):
    """Create the ticket with all collected information"""
    current_ticket = state["ticket"]
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    user_info = state.get("user_info", {})
    
    # Generate ticket ID and timestamp
    ticket_id = generate_ticket_id()
    created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Build final ticket
    final_ticket = current_ticket.model_copy(update={
        "ticket_id": ticket_id,
        "created_at": created_at,
        "user_id": user_info.get("user_id"),
        "user_name": user_info.get("user_name"),
        "email": user_info.get("email"),
        "phone": user_info.get("phone"),
        "department": user_info.get("department")
    })
    
    # In production: Save to database, send notifications, etc.
    print(f"\n[SYSTEM] Ticket Created: {final_ticket.model_dump_json(indent=2)}\n")
    
    success_message = f"""✅ **Ticket Created Successfully!**

**Ticket ID:** {ticket_id}
**Created:** {created_at}

Your ticket has been submitted and assigned to the IT Support team.
You will receive updates at {user_info.get('email', 'your registered email')}.

Is there anything else I can help you with?"""
    
    return {
        "messages": [AIMessage(content=success_message)],
        "ticket": create_empty_ticket(),
        "ticket_preview_shown": False,
        "awaiting_confirmation": False,
        "last_question": None,
        "current_extra_field_index": 0
    }
