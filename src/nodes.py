from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket, generate_ticket_id
import os
from datetime import datetime
from dotenv import load_dotenv
load_dotenv()

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# =============================================================================
# NODE 1: CHATBOT - General troubleshooting with KB
# =============================================================================
def chatbot_node(state: AgentState):
    """
    Main chatbot node - provides troubleshooting help and hands off to ticket system
    """
    messages = state["messages"]
    
    # Skip processing if we're in ticket collection mode
    last_question = state.get("last_question", None)
    awaiting_confirmation = state.get("awaiting_confirmation", False)
    
    # List of all possible ticket questions (base + category-specific)
    ticket_questions = ["category", "device", "priority", "description"]
    for template in FORM_TEMPLATES.values():
        ticket_questions.extend(template.get("extra_fields", []))
    
    if last_question in ticket_questions:
        return {}
    
    if awaiting_confirmation:
        return {}
    
    # Get KB from global scope
    from src.kb import get_global_kb, get_best_solution, detect_category
    kb = get_global_kb()
    
    user_message = messages[-1].content if messages else ""
    
    # Search KB for solutions
    kb_results = {"found": False, "solutions": [], "confidence": "low"}
    detected_cat = None
    
    if kb:
        try:
            detected_cat = detect_category(user_message)
            kb_results = get_best_solution(
                kb=kb,
                issue_description=user_message,
                conversation_history=[m.content for m in messages[:-1]],
                category=detected_cat
            )
            print(f"[DEBUG] KB search for: '{user_message[:50]}...', category: {detected_cat}")
            print(f"[DEBUG] KB results: found={kb_results['found']}, confidence={kb_results.get('confidence', 'N/A')}")
        except Exception as e:
            print(f"Warning: KB search failed: {e}")
    
    # Build system prompt based on KB results
    if kb_results["found"] and kb_results["confidence"] in ["high", "medium"]:
        kb_context = "\n\n".join([
            f"**Solution** (Relevance: {sol['similarity']:.0%}):\n{sol['content']}"
            for sol in kb_results["solutions"][:2]  # Top 2 solutions
        ])
        
        system_prompt = f"""You are an IT Support Chatbot.

KNOWLEDGE BASE SOLUTIONS FOUND:
{kb_context}

STRICT RULES:
1. Provide the solution steps from the knowledge base clearly
2. Format steps as numbered list
3. Ask: "Let me know if this helps!"
4. If user says it didn't work, still not working, or needs more help:
   Reply ONLY with: "handoff_to_ticket"
5. If user directly asks to create/file/submit a ticket:
   Reply ONLY with: "handoff_to_ticket"
6. Keep responses SHORT and focused on the solution

Do NOT mention tickets unless the user asks or says the solution didn't work.
"""
    else:
        system_prompt = """You are an IT Support Chatbot.

INSTRUCTIONS:
1. For IT issues: Provide 3-4 basic troubleshooting steps
2. Say "I couldn't find a specific solution, but here are general steps:"
3. Ask: "Let me know if this helps!"
4. If user says it didn't work or asks for a ticket:
   Reply ONLY with: "handoff_to_ticket"
5. If user directly asks to create/file/submit a ticket:
   Reply ONLY with: "handoff_to_ticket"

Keep responses SHORT and helpful.
Do NOT automatically offer tickets.
"""
    
    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    
    return {
        "messages": [response],
        "detected_category": detected_cat
    }


# =============================================================================
# NODE 2: TICKET COLLECTION - Collect ticket info step by step
# =============================================================================
def ticket_collection_node(state: AgentState):
    """
    Collect ticket information step by step with category-specific fields
    """
    current_ticket = state["ticket"]
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    user_devices = state["user_devices"]
    user_info = state.get("user_info", {})
    messages = state["messages"]
    last_user_message = messages[-1].content if messages else ""
    last_question = state.get("last_question", None)
    detected_category = state.get("detected_category", None)
    extra_field_index = state.get("current_extra_field_index", 0)
    
    llm_with_tools = llm.bind_tools([TicketSchema])
    
    # ---------------------------
    # STEP 1: Process user's response to previous question
    # ---------------------------
    
    # Handle category selection
    if last_question == "category":
        category_map = {
            "1": "Network", "network": "Network", "wifi": "Network", "internet": "Network", "vpn": "Network",
            "2": "Account", "account": "Account", "login": "Account", "password": "Account",
            "3": "Hardware", "hardware": "Hardware", "slow": "Hardware", "computer": "Hardware",
            "4": "Software", "software": "Software", "app": "Software", "application": "Software",
            "5": "Email", "email": "Email", "outlook": "Email", "mail": "Email",
            "6": "General", "general": "General", "other": "General"
        }
        user_choice = last_user_message.lower().strip()
        matched_category = category_map.get(user_choice, detected_category or "General")
        current_ticket = current_ticket.model_copy(update={"category": matched_category})
        last_question = None
    
    # Handle device selection
    if last_question == "device" and not current_ticket.device_id:
        extraction_prompt = f"""Extract device from user's message.
USER DEVICES: {user_devices}
USER'S MESSAGE: "{last_user_message}"
Match to one of the devices. Use TicketSchema tool to update device_id ONLY."""
        
        response = llm_with_tools.invoke([SystemMessage(content=extraction_prompt)])
        if response.tool_calls:
            new_data = response.tool_calls[0]['args']
            if 'device_id' in new_data:
                current_ticket = current_ticket.model_copy(update={'device_id': new_data['device_id']})
        last_question = None
    
    # Handle priority selection
    if last_question == "priority" and not current_ticket.priority:
        priority_map = {"low": "Low", "medium": "Medium", "high": "High", "critical": "Critical",
                       "1": "Low", "2": "Medium", "3": "High", "4": "Critical"}
        matched_priority = priority_map.get(last_user_message.lower().strip(), "Medium")
        current_ticket = current_ticket.model_copy(update={"priority": matched_priority})
        last_question = None
    
    # Handle description
    if last_question == "description":
        if any(word in last_user_message.lower() for word in ["no", "skip", "none", "nope"]):
            current_ticket = current_ticket.model_copy(update={"description": "None provided"})
        else:
            current_ticket = current_ticket.model_copy(update={"description": last_user_message})
        last_question = None
    
    # Handle category-specific extra fields
    if last_question and last_question not in ["category", "device", "priority", "description"]:
        # This is an extra field response
        extra_fields = current_ticket.extra_fields or {}
        if last_user_message.lower().strip() in ["no", "none", "skip", "n/a"]:
            extra_fields[last_question] = "N/A"
        else:
            extra_fields[last_question] = last_user_message
        current_ticket = current_ticket.model_copy(update={"extra_fields": extra_fields})
        extra_field_index += 1
        last_question = None
    
    # ---------------------------
    # STEP 2: Auto-fill fields from context
    # ---------------------------
    
    # Auto-fill user info from session (simulated)
    if not current_ticket.user_id and user_info:
        current_ticket = current_ticket.model_copy(update={
            "user_id": user_info.get("user_id"),
            "user_name": user_info.get("user_name"),
            "email": user_info.get("email"),
            "phone": user_info.get("phone"),
            "department": user_info.get("department")
        })
    
    # Auto-extract issue summary from conversation
    if not current_ticket.issue_summary:
        summary_prompt = """Extract a brief issue summary (5-10 words) from the conversation.
Use TicketSchema tool to update ONLY issue_summary field."""
        response = llm_with_tools.invoke([SystemMessage(content=summary_prompt)] + messages)
        if response.tool_calls:
            new_data = response.tool_calls[0]['args']
            if 'issue_summary' in new_data:
                current_ticket = current_ticket.model_copy(update={'issue_summary': new_data['issue_summary']})
    
    # Auto-set category from detected if not set
    if not current_ticket.category and detected_category:
        current_ticket = current_ticket.model_copy(update={"category": detected_category})
    
    # ---------------------------
    # STEP 3: Ask for missing required fields
    # ---------------------------
    
    # Ask for category if not set
    if not current_ticket.category:
        ask_message = """What category best describes your issue?

  1. **Network** - WiFi, Internet, VPN issues
  2. **Account** - Login, Password, MFA issues
  3. **Hardware** - Slow computer, Keyboard, Monitor
  4. **Software** - Application errors, Installation
  5. **Email** - Outlook, Email sending/receiving
  6. **General** - Other IT issues

Please choose (1-6 or type the category name):"""
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "category",
            "current_extra_field_index": extra_field_index
        }
    
    # Ask for device
    if not current_ticket.device_id:
        device_list = "\n".join([f"  • {device}" for device in user_devices])
        ask_message = f"Which device are you experiencing this issue with?\n\n{device_list}"
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "device",
            "current_extra_field_index": extra_field_index
        }
    
    # Ask for priority
    if not current_ticket.priority:
        ask_message = """What priority level should this ticket have?

  • **Low:** Can wait, minor inconvenience
  • **Medium:** Affecting work but have workaround
  • **High:** Blocking work, urgent
  • **Critical:** System down, major business impact

Please choose: Low, Medium, High, or Critical"""
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "priority",
            "current_extra_field_index": extra_field_index
        }
    
    # ---------------------------
    # STEP 4: Ask category-specific extra fields
    # ---------------------------
    category = current_ticket.category or "General"
    template = FORM_TEMPLATES.get(category, FORM_TEMPLATES["General"])
    extra_fields_list = template.get("extra_fields", [])
    current_extra_fields = current_ticket.extra_fields or {}
    
    # Find next unanswered extra field
    for i, field_name in enumerate(extra_fields_list):
        if field_name not in current_extra_fields:
            prompt = template["field_prompts"].get(field_name, f"Please provide {field_name}:")
            return {
                "messages": [AIMessage(content=prompt)],
                "ticket": current_ticket,
                "last_question": field_name,
                "current_extra_field_index": i
            }
    
    # ---------------------------
    # STEP 5: Ask for description (optional, last)
    # ---------------------------
    if not current_ticket.description:
        ask_message = "Would you like to add any additional details or notes? (Type 'no' to skip)"
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "description",
            "current_extra_field_index": extra_field_index
        }
    
    # All fields collected - ready for preview
    return {
        "messages": [AIMessage(content="Great! Let me show you a preview of your ticket...")],
        "ticket": current_ticket,
        "last_question": None,
        "current_extra_field_index": 0
    }


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
