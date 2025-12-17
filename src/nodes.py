from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.state import AgentState, TicketSchema
import os
from dotenv import load_dotenv
load_dotenv()


# Mock KB for "First Line of Defense" 
KB_ANSWERS = {
    "wifi": "1. Toggle Wifi on/off.\n2. Forget network 'SchoolWifi'.\n3. Restart device.",
    "login": "1. Clear browser cache.\n2. Try Incognito mode.\n3. Reset password."
}

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# --- NODE 1: The General Chatbot (Troubleshooter) ---
def chatbot_node(state: AgentState):
    messages = state["messages"]
    
    # CHECK: If we're in ticket collection mode or awaiting confirmation, skip chatbot processing
    last_question = state.get("last_question", None)
    awaiting_confirmation = state.get("awaiting_confirmation", False)
    
    # If we just asked a ticket question and user is responding, don't process in chatbot
    if last_question in ["device", "priority", "description"]:
        # User is responding to ticket collection question
        # Don't call LLM, just pass through (routing will handle it)
        return {}
    
    # If awaiting confirmation (preview shown), don't process in chatbot
    if awaiting_confirmation:
        return {}
    
    # Get KB from global scope (not from state, as it's not serializable)
    from src.kb import get_global_kb, get_best_solution, detect_category
    kb = get_global_kb()
    
    # Extract user's issue from latest message
    user_message = messages[-1].content if messages else ""
    
    # If KB is available, try to get relevant solutions
    kb_results = {"found": False, "solutions": [], "confidence": "low"}
    if kb:
        try:
            category = detect_category(user_message)
            kb_results = get_best_solution(
                kb=kb,
                issue_description=user_message,
                conversation_history=[m.content for m in messages[:-1]],
                category=category
            )
            # Debug: Show KB search results
            print(f"[DEBUG] KB search for: '{user_message}', category: {category}")
            print(f"[DEBUG] KB results: found={kb_results['found']}, confidence={kb_results.get('confidence', 'N/A')}")
            if kb_results.get('solutions'):
                print(f"[DEBUG] Top solution similarity: {kb_results['solutions'][0].get('similarity', 'N/A')}")
        except Exception as e:
            # Fallback gracefully if KB fails
            print(f"Warning: KB search failed: {e}")
    
    # Build system prompt with or without KB context
    if kb_results["found"] and kb_results["confidence"] in ["high", "medium"]:
        # Format KB solutions for LLM
        kb_context = "\n\n".join([
            f"**Solution {i+1}** (Similarity: {sol['similarity']:.2%}):\n{sol['content']}"
            for i, sol in enumerate(kb_results["solutions"])
        ])
        
        system_prompt = f"""You are an IT Support Chatbot.

        KNOWLEDGE BASE SOLUTIONS:
        {kb_context if kb_results["found"] else "No specific solution found in knowledge base."}

        STRICT RULES:
        1. If KB solution found: Provide ONLY the steps from the knowledge base, nothing more.
        - Copy the numbered steps exactly
        - Add a brief "Try these steps" intro
        - Do NOT elaborate or add extra explanations

        2. If NO KB solution found: Say "I couldn't find a specific solution, but here are general steps:" 
        Then provide 3-4 basic troubleshooting steps only.

        3. After providing steps, ask: "Let me know if this helps!"

        4. If user says "didn't work", "still not working", "issue persists":
        Ask: "Would you like me to create a support ticket for this issue? (yes/no)"

        5. If user replies "yes", "sure", "please", "ok" to ticket question:
        Reply ONLY with: "handoff_to_ticket"

        6. If user says "no": 
        Ask what else you can help with.

        7. NEVER mention tickets unless user indicates solution didn't work.

        Keep all responses SHORT and DIRECT.
        """
    else:
        # Fallback to generic prompt
        system_prompt = f"""
        You are an IT Support Chatbot. 

        INSTRUCTIONS:
        1. If KB solution found: Provide ONLY the steps from the knowledge base, nothing more.
        - Copy the numbered steps exactly
        - Add a brief "Try these steps" intro
        - Do NOT elaborate or add extra explanations

        2. If NO KB solution found: Say "I couldn't find a specific solution, but here are general steps:" 
        Then provide 3-4 basic troubleshooting steps only.

        3. After providing steps, ask: "Let me know if this helps!"

        4. If user says "didn't work", "still not working", "issue persists":
        Ask: "Would you like me to create a support ticket for this issue? (yes/no)"

        5. If user replies "yes", "sure", "please", "ok" to ticket question:
        Reply ONLY with: "handoff_to_ticket"

        6. If user says "no": 
        Ask what else you can help with.

        7. NEVER mention tickets unless user indicates solution didn't work.

        Keep all responses SHORT and DIRECT.
        """
    
    # Invoke LLM
    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    
    return {"messages": [response]}


# # --- NODE 2: The Ticket Agent (Form Filler) ---
# def ticket_agent_node(state: AgentState):
#     current_ticket = state["ticket"]
#     # Convert dict to TicketSchema if needed
#     if isinstance(current_ticket, dict):
#         current_ticket = TicketSchema(**current_ticket)
    
#     user_devices = state["user_devices"]
    
#     # 1. DEFINE TOOLS for extraction
#     # We use the schema to force the LLM to extract data
#     llm_with_tools = llm.bind_tools([TicketSchema])
    
#     # 2. CONSTRUCT PROMPT
#     # We give the LLM the current form state so it knows what is missing
#     system_prompt = f"""
#     You are the Ticket Filing Agent.
    
#     CURRENT TICKET STATE:
#     {current_ticket.model_dump_json(exclude_none=True)}
    
#     USER DEVICES: {user_devices}
    
#     GOAL: Fill missing fields.
#     1. If 'device_id' is missing and user has multiple devices, ask "Which device?".
#     2. If 'issue_summary' is missing, extract it from history.
#     3. If everything is found, set 'is_complete' to True.
#     """
    
#     response = llm_with_tools.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    
#     # 3. HANDLE UPDATES (Tool Calling)
#     if response.tool_calls:
#         # LLM wants to update the ticket!
#         new_data = response.tool_calls[0]['args']
#         updated_ticket = current_ticket.model_copy(update=new_data)
        
#         # Create a ToolMessage to respond to the tool call
#         tool_message = ToolMessage(
#             content=f"Ticket updated successfully: {updated_ticket.model_dump_json(exclude_none=True)}",
#             tool_call_id=response.tool_calls[0]['id']
#         )
        
#         # Return both the tool call message and the tool response
#         return {
#             "messages": [response, tool_message],
#             "ticket": updated_ticket
#         }
    
#     # If no tool call, it's a question to the user (e.g. "What is your device?")
#     return {"messages": [response]}

# --- NODE 2: The Ticket Agent (Form Filler) ---
def ticket_collection_node(state: AgentState):
    """
    Phase 1: Collect ticket information step by step
    """
    current_ticket = state["ticket"]
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    user_devices = state["user_devices"]
    messages = state["messages"]
    last_user_message = messages[-1].content if messages else ""
    last_question = state.get("last_question", None)
    
    llm_with_tools = llm.bind_tools([TicketSchema])
    
    # STEP 1: If we just asked a question, extract the answer from user's response
    if last_question == "device" and not current_ticket.device_id:
        # User is responding to device question
        extraction_prompt = f"""Extract device selection from user's message.

USER DEVICES: {user_devices}
USER'S MESSAGE: "{last_user_message}"

TASK: Match the user's response to one of the devices.
- If they said "Dell", "dell", "latitude", match to "Dell Latitude 5420"
- If they said "iPad", "ipad", "pro", match to "iPad Pro"
- Use EXACT device name from list

Use TicketSchema tool to update device_id ONLY. Do NOT update any other fields.
"""
        response = llm_with_tools.invoke([SystemMessage(content=extraction_prompt)] + messages)
        
        if response.tool_calls:
            new_data = response.tool_calls[0]['args']
            # Only update device_id
            if 'device_id' in new_data:
                current_ticket = current_ticket.model_copy(update={'device_id': new_data['device_id']})
                # Clear last_question so we proceed to next field
                last_question = None
    
    if last_question == "priority" and not current_ticket.priority:
        # User is responding to priority question
        extraction_prompt = f"""Extract priority from user's message.

USER'S MESSAGE: "{last_user_message}"

TASK: Extract priority level: Low, Medium, High, or Critical
Use TicketSchema tool to update priority ONLY. Do NOT update any other fields.
"""
        response = llm_with_tools.invoke([SystemMessage(content=extraction_prompt)] + messages)
        
        if response.tool_calls:
            new_data = response.tool_calls[0]['args']
            # Only update priority
            if 'priority' in new_data:
                current_ticket = current_ticket.model_copy(update={'priority': new_data['priority']})
                # Clear last_question so we proceed to next field
                last_question = None
    
    if last_question == "description":
        # User is responding to description question
        if any(word in last_user_message.lower() for word in ["no", "skip", "nope", "none"]):
            current_ticket = current_ticket.model_copy(update={"description": "None provided"})
        else:
            # User provided actual description
            current_ticket = current_ticket.model_copy(update={"description": last_user_message})
        # Clear last_question
        last_question = None
    
    # STEP 2: Extract issue summary ONLY if missing (from conversation history)
    if not current_ticket.issue_summary:
        summary_prompt = f"""Extract ONLY the issue summary from conversation history.

Look through all messages and identify what problem the user reported (laptop slow, wifi issues, etc).
Create a brief 5-10 word summary.

IMPORTANT: Use TicketSchema tool to update ONLY the issue_summary field. Do NOT fill description field.
"""
        response = llm_with_tools.invoke([SystemMessage(content=summary_prompt)] + messages)
        
        if response.tool_calls:
            new_data = response.tool_calls[0]['args']
            # Only update issue_summary, ignore any other fields LLM might try to fill
            if 'issue_summary' in new_data:
                current_ticket = current_ticket.model_copy(update={'issue_summary': new_data['issue_summary']})
    
    # STEP 3: Check what's still missing and ask for it
    
    # Check if device is missing
    if not current_ticket.device_id:
        # Use fixed message instead of LLM to avoid weird responses
        device_list = "\n".join([f"  • {device}" for device in user_devices])
        ask_message = f"Which device are you experiencing this issue with?\n\n{device_list}"
        
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "device"  # Track that we asked for device
        }
    
    # Check if priority is missing
    if not current_ticket.priority:
        # Use fixed message
        ask_message = """What priority level should this ticket have?

  • **Low:** Can wait, minor inconvenience
  • **Medium:** Affecting work but have workaround  
  • **High:** Blocking work, urgent
  • **Critical:** System down, business impact

Please choose: Low, Medium, High, or Critical"""
        
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "priority"  # Track that we asked for priority
        }
    
    # Check if description is missing (optional field)
    if not current_ticket.description:
        # Use fixed message
        ask_message = "Would you like to add any additional details or description to the ticket? (You can say 'no' to skip)"
        
        return {
            "messages": [AIMessage(content=ask_message)],
            "ticket": current_ticket,
            "last_question": "description"  # Track that we asked for description
        }
    
    # All fields collected - ready for preview
    return {
        "messages": [AIMessage(content="Great! Let me show you a preview of the ticket...")],
        "ticket": current_ticket,
        "last_question": None  # Clear the question tracker
    }
    

def ticket_preview_node(state: AgentState):
    """
    Phase 2: Show ticket preview and ask for confirmation
    """
    current_ticket = state["ticket"]
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    # Format ticket preview
    preview = f"""
📋 **Ticket Preview**

**Issue Summary:** {current_ticket.issue_summary or "Not provided"}
**Device:** {current_ticket.device_id or "Not provided"}
**Priority:** {current_ticket.priority or "Not provided"}
**Description:** {current_ticket.description or "None"}

---

Please review the information above.

**Options:**
- Type "submit" or "yes" to create the ticket
- Type "edit" to make changes
- Type "cancel" to cancel and return to chat

What would you like to do?
"""
    
    return {
        "messages": [AIMessage(content=preview)],
        "ticket_preview_shown": True,
        "awaiting_confirmation": True
    }


def ticket_confirmation_node(state: AgentState):
    """
    Phase 3: Handle user's confirmation response
    """
    messages = state["messages"]
    last_user_message = messages[-1].content.lower().strip()
    
    # Check what user wants to do
    if any(word in last_user_message for word in ["submit", "yes", "confirm", "ok", "proceed"]):
        # User confirmed - ready to submit
        return {
            "messages": [AIMessage(content="Creating your ticket...")],
            "confirmation_action": "submit",
            "awaiting_confirmation": False
        }
    
    elif "edit" in last_user_message or "change" in last_user_message:
        # User wants to edit
        prompt = "What would you like to change? Tell me the field and new value."
        return {
            "messages": [AIMessage(content=prompt)],
            "confirmation_action": "edit",
            "awaiting_confirmation": False
        }
    
    elif any(word in last_user_message for word in ["cancel", "no", "nevermind", "back"]):
        # User wants to cancel - reset ticket properly
        return {
            "messages": [AIMessage(content="Ticket creation cancelled. How else can I help you?")],
            "confirmation_action": "cancel",
            "ticket": {
                "issue_summary": None,
                "device_id": None,
                "priority": None,
                "description": None
            },
            "ticket_preview_shown": False,
            "awaiting_confirmation": False
        }
    
    else:
        # User's response unclear - stay in confirmation mode
        return {
            "messages": [AIMessage(content="Please respond with: submit, edit, or cancel")],
            "confirmation_action": "",
            "awaiting_confirmation": True  # Keep in confirmation mode
        }