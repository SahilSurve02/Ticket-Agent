"""
Multi-Agent System for IT Support
- ChatbotAgent: Handles troubleshooting and KB queries
- TicketAgent: Handles ticket creation and management
"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List
from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket
from src.kb import get_global_kb, get_best_solution, detect_category
import os
from dotenv import load_dotenv
load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)


# =============================================================================
# AGENT 1: CHATBOT AGENT - Troubleshooting & KB Search
# =============================================================================

class ChatbotAgent:
    """
    Specialized agent for IT troubleshooting using knowledge base
    Responsibilities:
    - Search KB for solutions
    - Provide troubleshooting steps
    - Detect when user needs ticket escalation
    """
    
    def __init__(self):
        self.name = "Chatbot Agent"
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
    
    def process(self, state: AgentState) -> Dict:
        """Main processing function for chatbot agent"""
        messages = state["messages"]
        user_message = messages[-1].content if messages else ""
        
        # Get KB
        kb = get_global_kb()
        
        # Search for solutions
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
                print(f"[ChatbotAgent] Detected category: {detected_cat}")
                print(f"[ChatbotAgent] KB found: {kb_results['found']}, confidence: {kb_results.get('confidence')}")
            except Exception as e:
                print(f"[ChatbotAgent] KB search error: {e}")
        
        # Build system prompt
        if kb_results["found"] and kb_results["confidence"] in ["high", "medium"]:
            kb_context = "\n\n".join([
                f"**Solution** (Relevance: {sol['similarity']:.0%}):\n{sol['content']}"
                for sol in kb_results["solutions"][:2]
            ])
            
            system_prompt = f"""You are the IT Support Chatbot Agent.

KNOWLEDGE BASE SOLUTIONS:
{kb_context}

YOUR ROLE:
1. Provide clear troubleshooting steps from the KB
2. Format as numbered list
3. Ask: "Let me know if this helps!"
4. If user says solution didn't work or needs more help:
   Say EXACTLY: "I'll transfer you to our Ticket Agent to create a support ticket."
   Then add: "HANDOFF_TO_TICKET_AGENT"
5. If user directly asks to create/file/submit a ticket:
   Say EXACTLY: "I'll transfer you to our Ticket Agent."
   Then add: "HANDOFF_TO_TICKET_AGENT"

Keep responses SHORT and solution-focused.
"""
        else:
            system_prompt = """You are the IT Support Chatbot Agent.

YOUR ROLE:
1. Provide 3-4 general troubleshooting steps for IT issues
2. Say: "I couldn't find a specific solution, but here are general steps:"
3. Ask: "Let me know if this helps!"
4. If user says it didn't work or asks for a ticket:
   Say EXACTLY: "I'll transfer you to our Ticket Agent to create a support ticket."
   Then add: "HANDOFF_TO_TICKET_AGENT"
5. If user directly asks to create/file/submit a ticket:
   Say EXACTLY: "I'll transfer you to our Ticket Agent."
   Then add: "HANDOFF_TO_TICKET_AGENT"

Keep responses SHORT and helpful.
"""
        
        response = self.llm.invoke([SystemMessage(content=system_prompt)] + messages)
        
        return {
            "messages": [response],
            "detected_category": detected_cat,
            "kb_used": kb_results["found"],
            "kb_confidence": kb_results.get("confidence", "none")
        }


# =============================================================================
# AGENT 2: TICKET AGENT - Ticket Creation & Management
# =============================================================================

class TicketAgent:
    """
    Specialized agent for ticket creation and management
    Responsibilities:
    - Collect ticket information step-by-step
    - Handle category-specific fields
    - Generate ticket preview
    - Submit tickets
    """
    
    def __init__(self):
        self.name = "Ticket Agent"
        self.llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)
        self.llm_with_tools = self.llm.bind_tools([TicketSchema])
    
    def process_ticket_collection(self, state: AgentState) -> Dict:
        """Collect ticket information step by step"""
        current_ticket = state["ticket"]
        if isinstance(current_ticket, dict):
            current_ticket = TicketSchema(**current_ticket)
        
        user_devices = state["user_devices"]
        user_info = state.get("user_info", {})
        messages = state["messages"]
        last_user_message = messages[-1].content if messages else ""
        last_question = state.get("last_question")
        detected_category = state.get("detected_category")
        extra_field_index = state.get("current_extra_field_index", 0)
        
        # Process previous response
        updated_ticket, new_last_question, new_extra_index = self._process_user_response(
            current_ticket, last_question, last_user_message, 
            user_devices, detected_category, extra_field_index, messages
        )
        
        # Auto-fill fields
        updated_ticket = self._auto_fill_fields(updated_ticket, user_info, detected_category, messages)
        
        # Check for missing fields and ask next question
        return self._ask_next_field(updated_ticket, user_devices, new_extra_index, state)
    
    def _process_user_response(self, ticket, last_question, user_msg, 
                                user_devices, detected_cat, extra_idx, messages):
        """Process user's response to previous question"""
        
        # Category selection
        if last_question == "category":
            category_map = {
                "1": "Network", "network": "Network", "wifi": "Network",
                "2": "Account", "account": "Account", "login": "Account",
                "3": "Hardware", "hardware": "Hardware", "slow": "Hardware",
                "4": "Software", "software": "Software", "app": "Software",
                "5": "Email", "email": "Email", "outlook": "Email",
                "6": "General", "general": "General", "other": "General"
            }
            matched = category_map.get(user_msg.lower().strip(), detected_cat or "General")
            ticket = ticket.model_copy(update={"category": matched})
            return ticket, None, extra_idx
        
        # Device selection
        if last_question == "device" and not ticket.device_id:
            for device in user_devices:
                if any(word in user_msg.lower() for word in device.lower().split()):
                    ticket = ticket.model_copy(update={"device_id": device})
                    break
            return ticket, None, extra_idx
        
        # Priority selection
        if last_question == "priority" and not ticket.priority:
            priority_map = {
                "low": "Low", "medium": "Medium", "high": "High", "critical": "Critical",
                "1": "Low", "2": "Medium", "3": "High", "4": "Critical"
            }
            matched = priority_map.get(user_msg.lower().strip(), "Medium")
            ticket = ticket.model_copy(update={"priority": matched})
            return ticket, None, extra_idx
        
        # Description
        if last_question == "description":
            if any(word in user_msg.lower() for word in ["no", "skip", "none", "nope"]):
                ticket = ticket.model_copy(update={"description": "None provided"})
            else:
                ticket = ticket.model_copy(update={"description": user_msg})
            return ticket, None, extra_idx
        
        # Extra fields
        if last_question and last_question not in ["category", "device", "priority", "description"]:
            extra_fields = ticket.extra_fields or {}
            if user_msg.lower().strip() in ["no", "none", "skip", "n/a"]:
                extra_fields[last_question] = "N/A"
            else:
                extra_fields[last_question] = user_msg
            ticket = ticket.model_copy(update={"extra_fields": extra_fields})
            return ticket, None, extra_idx + 1
        
        return ticket, last_question, extra_idx
    
    def _auto_fill_fields(self, ticket, user_info, detected_cat, messages):
        """Auto-fill fields from context"""
        # User info
        if not ticket.user_id and user_info:
            ticket = ticket.model_copy(update={
                "user_id": user_info.get("user_id"),
                "user_name": user_info.get("user_name"),
                "email": user_info.get("email"),
                "phone": user_info.get("phone"),
                "department": user_info.get("department")
            })
        
        # Issue summary
        if not ticket.issue_summary:
            summary_prompt = """Extract brief issue summary (5-10 words) from conversation.
Use TicketSchema tool to update ONLY issue_summary."""
            response = self.llm_with_tools.invoke([SystemMessage(content=summary_prompt)] + messages)
            if response.tool_calls:
                new_data = response.tool_calls[0]['args']
                if 'issue_summary' in new_data:
                    ticket = ticket.model_copy(update={'issue_summary': new_data['issue_summary']})
        
        # Category
        if not ticket.category and detected_cat:
            ticket = ticket.model_copy(update={"category": detected_cat})
        
        return ticket
    
    def _ask_next_field(self, ticket, user_devices, extra_idx, state):
        """Ask for next missing field"""
        
        # Category
        if not ticket.category:
            msg = """What category best describes your issue?

  1. **Network** - WiFi, Internet, VPN
  2. **Account** - Login, Password, MFA
  3. **Hardware** - Computer/Device issues
  4. **Software** - Application errors
  5. **Email** - Outlook, Email issues
  6. **General** - Other IT issues

Choose (1-6 or type name):"""
            return {
                "messages": [AIMessage(content=msg)],
                "ticket": ticket,
                "last_question": "category",
                "current_extra_field_index": extra_idx
            }
        
        # Device
        if not ticket.device_id:
            device_list = "\n".join([f"  • {d}" for d in user_devices])
            msg = f"Which device is affected?\n\n{device_list}"
            return {
                "messages": [AIMessage(content=msg)],
                "ticket": ticket,
                "last_question": "device",
                "current_extra_field_index": extra_idx
            }
        
        # Priority
        if not ticket.priority:
            msg = """Priority level?

  • **Low:** Can wait
  • **Medium:** Affecting work
  • **High:** Blocking work
  • **Critical:** System down

Choose: Low, Medium, High, or Critical"""
            return {
                "messages": [AIMessage(content=msg)],
                "ticket": ticket,
                "last_question": "priority",
                "current_extra_field_index": extra_idx
            }
        
        # Category-specific fields
        category = ticket.category or "General"
        template = FORM_TEMPLATES.get(category, FORM_TEMPLATES["General"])
        extra_fields_list = template.get("extra_fields", [])
        current_extras = ticket.extra_fields or {}
        
        for field_name in extra_fields_list:
            if field_name not in current_extras:
                prompt = template["field_prompts"].get(field_name, f"Please provide {field_name}:")
                return {
                    "messages": [AIMessage(content=prompt)],
                    "ticket": ticket,
                    "last_question": field_name,
                    "current_extra_field_index": extra_idx
                }
        
        # Description
        if not ticket.description:
            msg = "Any additional details? (Type 'no' to skip)"
            return {
                "messages": [AIMessage(content=msg)],
                "ticket": ticket,
                "last_question": "description",
                "current_extra_field_index": extra_idx
            }
        
        # All done - ready for preview
        return {
            "messages": [AIMessage(content="Perfect! Let me show you the ticket preview...")],
            "ticket": ticket,
            "last_question": None,
            "current_extra_field_index": 0,
            "ticket_collection_complete": True
        }


# Global agent instances
chatbot_agent = ChatbotAgent()
ticket_agent = TicketAgent()


def get_chatbot_agent() -> ChatbotAgent:
    """Get the global chatbot agent instance"""
    return chatbot_agent


def get_ticket_agent() -> TicketAgent:
    """Get the global ticket agent instance"""
    return ticket_agent
