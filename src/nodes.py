"""
LangGraph Nodes for IT Support Chatbot

Each node represents a step in the conversation workflow.
Nodes delegate to specialized agents and handle state transitions.
"""

import logging
import json
import os
from datetime import datetime
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket, generate_ticket_id
from src.agents import get_chatbot_agent, get_ticket_agent
from src.db import save_ticket, check_for_duplicate_ticket
from dotenv import load_dotenv

load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Initialize LLM with exception handling
try:
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)
except Exception as e:
    logger.error(f"Failed to initialize LLM in nodes: {e}")
    raise

# Ticket storage file path
TICKETS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "tickets.json")


# =============================================================================
# NODE 1: CHATBOT - Uses dedicated ChatbotAgent
# =============================================================================
def chatbot_node(state: AgentState):
    """
    Chatbot node - delegates to ChatbotAgent for troubleshooting.
    
    Args:
        state: Current agent state.
        
    Returns:
        Updated state dictionary.
    """
    try:
        # Skip if in edit mode - let ticket_collection handle it
        if state.get("edit_mode"):
            return {}
        
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
    
    except Exception as e:
        logger.error(f"Error in chatbot_node: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="I apologize, but I encountered an error. Please try again.")]
        }


# =============================================================================
# NODE 2: TICKET COLLECTION - Uses dedicated TicketAgent
# =============================================================================
def ticket_collection_node(state: AgentState):
    """
    Ticket collection node - delegates to TicketAgent for ticket management.
    
    Args:
        state: Current agent state.
        
    Returns:
        Updated state dictionary.
    """
    try:
        # Delegate to TicketAgent
        agent = get_ticket_agent()
        result = agent.process_ticket_collection(state)
        
        # Clear the escalation flag after processing (prevent re-triggering)
        result["escalate_to_ticket"] = False
        
        return result
    
    except Exception as e:
        logger.error(f"Error in ticket_collection_node: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="I apologize, but I encountered an error processing your ticket. Please try again.")],
            "escalate_to_ticket": False
        }


# =============================================================================
# NODE 3: TICKET PREVIEW - Show formatted ticket preview
# =============================================================================
def ticket_preview_node(state: AgentState):
    """Show ticket preview and ask for confirmation"""
    try:
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
                extra_display += f"**{label}:** {value}  \n"
        
        # Format description nicely (ensure proper newlines)
        description = current_ticket.description or "None"
        if description != "None":
            # Replace escaped newlines with actual newlines for proper markdown rendering
            description = description.replace('\\n', '\n')
        
        # Get device name (ensure it's a string)
        device_name = str(current_ticket.device_id) if current_ticket.device_id else "Not provided"
        
        preview = f"""
📋 **Ticket Preview**

### 👤 User Information
**Name:** {user_info.get('user_name', 'N/A')}  
**Email:** {user_info.get('email', 'N/A')}  
**Phone:** {user_info.get('phone', 'N/A')}  
**Department:** {user_info.get('department', 'N/A')}

### 🎫 Issue Details
**Category:** {template['name']}  
**Issue Summary:** {current_ticket.issue_summary or "Not provided"}  
**Device:** {device_name}  
**Priority:** {current_ticket.priority or "Medium"}  
{extra_display}**Description:**  
{description}

**Options:**
• Type **"submit"** to create the ticket
• Type **"edit"** to make changes
• Type **"cancel"** to cancel

What would you like to do?
"""
        
        return {
            "messages": [AIMessage(content=preview)],
            "ticket_preview_shown": True,
            "awaiting_confirmation": True,
            "ticket_collection_complete": False,
            "edit_mode": False
        }
    except Exception as e:
        logger.error(f"Error in ticket_preview_node: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="I encountered an issue generating the ticket preview. Please try again or type 'cancel' to start over.")],
            "awaiting_confirmation": True
        }


# =============================================================================
# NODE 4: TICKET CONFIRMATION - Handle submit/edit/cancel
# =============================================================================
def ticket_confirmation_node(state: AgentState):
    """Handle user's confirmation response"""
    try:
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
                "messages": [AIMessage(content="What would you like to change? (e.g., 'change priority to ...' or 'change device to ...')")],
                "confirmation_action": "",  # Clear action so we don't loop
                "edit_mode": True,  # Set edit mode so next user message is processed as edit
                "awaiting_confirmation": False  # Not awaiting submit/edit/cancel anymore
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
    except Exception as e:
        logger.error(f"Error in ticket_confirmation_node: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="I encountered an issue processing your response. Please respond with: **submit**, **edit**, or **cancel**")],
            "awaiting_confirmation": True
        }


# =============================================================================
# NODE 5: SUBMIT TICKET - Create the final ticket and save to file
# =============================================================================
def submit_ticket_node(state: AgentState):
    """Create the ticket with all collected information and save to file"""
    try:
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
        
        # Convert to dict for storage
        ticket_dict = final_ticket.model_dump()
        
        # Save to database
        saved = save_ticket(ticket_dict)

        # Handle Database Failure (FR-022)
        if not saved:
            logger.error("Failed to save ticket to database")
            return {
                "messages": [AIMessage(content="❌ System Error: Could not save ticket to database. Please type **'submit'** to try again.")],
                # Do NOT clear the ticket here, so user can retry
                "awaiting_confirmation": True,
                "confirmation_action": "submit"
            }

        
        # Log ticket creation for debugging
        logger.info(f"Ticket Created: {ticket_id}")
        
        success_message = f"""✅ **Ticket Created Successfully!**

**Ticket ID:** `{ticket_id}`  
**Created:** {created_at}  
**Priority:** {final_ticket.priority}  
**Category:** {final_ticket.category}

---

Your ticket has been submitted and assigned to the IT Support team.  
📧 Updates will be sent to: **{user_info.get('email', 'your registered email')}**

---

Is there anything else I can help you with?"""
        
        return {
            "messages": [AIMessage(content=success_message)],
            "ticket": create_empty_ticket(),
            "ticket_preview_shown": False,
            "awaiting_confirmation": False,
            "last_question": None,
            "current_extra_field_index": 0,
            "edit_mode": False,
            "ticket_collection_complete": False
        }
    except Exception as e:
        logger.error(f"Error in submit_ticket_node: {e}", exc_info=True)
        return {
            "messages": [AIMessage(content="❌ An unexpected error occurred while creating your ticket. Please type **'submit'** to try again or **'cancel'** to start over.")],
            "awaiting_confirmation": True
        }
