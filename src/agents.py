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
        awaiting_ticket_confirmation = state.get("awaiting_ticket_confirmation", False)
        
        # Handle ticket creation confirmation
        if awaiting_ticket_confirmation:
            response_lower = user_message.lower().strip()
            
            # User confirms ticket creation
            if any(word in response_lower for word in ["yes", "yeah", "yep", "sure", "ok", "okay", "please", "yup"]):
                msg = "I'll transfer you to our Ticket Agent to create a support ticket.\n\nHANDOFF_TO_TICKET_AGENT"
                print(f"[ChatbotAgent] User confirmed ticket creation, handing off to TicketAgent")
                # Try to pre-fill obvious ticket fields (device, priority) from recent conversation
                prefill = {}
                try:
                    user_devices = state.get("user_devices", []) or []
                    # Look at the last few messages for mentions
                    convo_text = " ".join([m.content for m in messages[-3:]]).lower()

                    # Detect device by matching tokens from known user devices
                    for device in user_devices:
                        dev_lower = device.lower()
                        if dev_lower in convo_text or any(tok in convo_text for tok in dev_lower.split()):
                            prefill["device_id"] = device
                            break

                    # Detect priority words or numeric choices (prefer strongest match)
                    priority_map = {
                        "4": "Critical", "3": "High", "2": "Medium", "1": "Low",
                        "critical": "Critical", "system down": "Critical",
                        "high": "High", "urgent": "High", "blocking": "High", "blocking work": "High",
                        "medium": "Medium", "moderate": "Medium",
                        "low": "Low", "can wait": "Low"
                    }
                    for key in ["system down", "critical", "urgent", "blocking work", "blocking", "high", "3", "medium", "2", "low", "1"]:
                        if key in convo_text:
                            prefill["priority"] = priority_map.get(key)
                            break
                except Exception:
                    prefill = {}

                # Merge prefill into existing ticket state (dict or TicketSchema)
                ticket_obj = state.get("ticket") or create_empty_ticket()
                if isinstance(ticket_obj, dict):
                    ticket_obj.update(prefill)
                else:
                    try:
                        ticket_obj = ticket_obj.model_copy(update=prefill)
                    except Exception:
                        ticket_obj = ticket_obj

                return {
                    "messages": [AIMessage(content=msg)],
                    "awaiting_ticket_confirmation": False,
                    "ticket": ticket_obj
                }
            
            # User declines ticket creation
            elif any(word in response_lower for word in ["no", "nope", "nah", "cancel", "nevermind", "never mind"]):
                msg = "No problem! Is there anything else I can help you with?"
                print(f"[ChatbotAgent] User declined ticket creation, staying in chatbot mode")
                return {
                    "messages": [AIMessage(content=msg)],
                    "awaiting_ticket_confirmation": False
                }
            
            # Unclear response - ask again
            else:
                msg = "I didn't quite catch that. Would you like me to create a support ticket? (yes/no)"
                return {
                    "messages": [AIMessage(content=msg)],
                    "awaiting_ticket_confirmation": True
                }
        
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
        
        # Check if user is reporting solution didn't work (ambiguous feedback)
        is_ambiguous_feedback = self._is_ambiguous_feedback(user_message, messages)
        
        # Check if user explicitly wants a ticket
        wants_ticket = any(word in user_message.lower() for word in [
            "create ticket", "file ticket", "submit ticket", "open ticket", 
            "ticket", "escalate", "need help", "didn't work", "doesn't work",
            "not working", "still broken", "still issue", "not fixed"
        ])
        
        print(f"[ChatbotAgent] Ambiguous feedback: {is_ambiguous_feedback}, Wants ticket: {wants_ticket}")
        
        # If user gives ambiguous feedback or explicitly wants ticket -> ASK FIRST
        if is_ambiguous_feedback or wants_ticket:
            msg = "Would you like me to create a support ticket for this issue? I can help you file it with our support team. (yes/no)"
            print(f"[ChatbotAgent] Asking user for ticket confirmation")
            return {
                "messages": [AIMessage(content=msg)],
                "detected_category": detected_cat,
                "awaiting_ticket_confirmation": True
            }
        
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
                1. Provide clear troubleshooting steps from the knowledge base.
                2. Format as numbered list
                3. Ask: "Let me know if this helps!"

                Keep responses SHORT and solution-focused.
                DO NOT mention tickets or escalation - I handle that separately.
                """
        else:
            system_prompt = """You are the IT Support Chatbot Agent.

                YOUR ROLE:
                1. Do not provide solutions from your knowledge base.
                2. Say: "I couldn't find a specific solution, could you please provide more details about the issue?"

                Keep responses SHORT and helpful.
                DO NOT mention tickets or escalation - I handle that separately.
                """
        
        response = self.llm.invoke([SystemMessage(content=system_prompt)] + messages)
        
        return {
            "messages": [response],
            "detected_category": detected_cat,
            "kb_used": kb_results["found"],
            "kb_confidence": kb_results.get("confidence", "none")
        }
    
    def _is_ambiguous_feedback(self, user_message: str, messages: List) -> bool:
        """
        Detect if user is giving ambiguous feedback about solution effectiveness
        (e.g., "kind of helped", "partially worked", "sort of")
        """
        # Only check if we previously provided a solution
        if len(messages) < 2:
            return False
        
        # Check if previous bot message was a solution
        prev_bot_msg = None
        for i in range(len(messages) - 2, -1, -1):
            if isinstance(messages[i], AIMessage):
                prev_bot_msg = messages[i].content
                break
        
        if not prev_bot_msg or "Let me know if this helps!" not in prev_bot_msg:
            return False
        
        # Detect ambiguous feedback phrases
        user_lower = user_message.lower().strip()
        ambiguous_phrases = [
            "kind of", "kinda", "sort of", "sorta", "partially", "partly",
            "somewhat", "a little", "a bit", "not completely", "not fully",
            "helped a little", "helped some", "only helped", "barely helped"
        ]
        
        return any(phrase in user_lower for phrase in ambiguous_phrases)


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
        """Collect ticket information step by step or handle edits"""
        current_ticket = state["ticket"]
        if isinstance(current_ticket, dict):
            current_ticket = TicketSchema(**current_ticket)

        messages = state["messages"]
        
        # Get the last HUMAN message (not AI message)
        last_user_message = ""
        for m in reversed(messages):
            if isinstance(m, HumanMessage):
                last_user_message = m.content
                break

        # Check if we're in edit mode (user said "edit" and now providing what to change)
        is_edit_mode = state.get("edit_mode", False)
        
        if is_edit_mode:
            print(f"[TicketAgent] Processing edit request: {last_user_message}")
            
            # Get available devices for context
            user_devices = state.get("user_devices", [])
            devices_list = ", ".join(user_devices) if user_devices else "Not available"
            
            edit_prompt = f"""You are an editing assistant. The user wants to change ticket details.
Based on their request, identify the fields to update and their new values.
Use the TicketSchema tool to apply these changes.

**AVAILABLE DEVICES:** {devices_list}

**IMPORTANT INSTRUCTIONS:**
- Use the correct, top-level fields for 'category', 'device_id', 'priority', and 'description'.
- Do NOT place these core fields inside the 'extra_fields' dictionary.
- 'extra_fields' is ONLY for category-specific fields that are NOT part of the main schema.
- For device_id, match to the closest device from the available devices list.

Map category to: "Network", "Account", "Hardware", "Software", "Email", "General".
Map priority to: "Low", "Medium", "High", "Critical".

Return the updated fields only.
"""
            response = self.llm_with_tools.invoke([
                SystemMessage(content=edit_prompt),
                HumanMessage(content=last_user_message)
            ])
            
            updated_ticket = current_ticket
            if response.tool_calls:
                new_data = response.tool_calls[0]['args']
                # Filter out None values to avoid overwriting
                new_data = {k: v for k, v in new_data.items() if v is not None}
                print(f"[TicketAgent] Extracted changes: {new_data}")
                updated_ticket = current_ticket.model_copy(update=new_data)
            else:
                print(f"[TicketAgent] No changes extracted from: {last_user_message}")
            
            # Return to preview with updated ticket, exit edit mode
            return {
                "messages": [AIMessage(content="I've updated the ticket. Here's the revised preview...")],
                "ticket": updated_ticket,
                "edit_mode": False,
                "confirmation_action": None,
                "ticket_collection_complete": True  # Go to preview
            }

        # --- Existing Logic ---
        user_devices = state["user_devices"]
        user_info = state.get("user_info", {})
        last_question = state.get("last_question")
        detected_category = state.get("detected_category")
        extra_field_index = state.get("current_extra_field_index", 0)
        
        # Process previous response
        updated_ticket, new_last_question, new_extra_index = self._process_user_response(
            current_ticket, last_question, last_user_message, 
            user_devices, detected_category, extra_field_index, messages
        )
        
        # Auto-fill fields
        updated_ticket = self._auto_fill_fields(updated_ticket, user_info, detected_category, messages, user_devices)
        
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
        
        # Device selection with validation
        if last_question == "device" and not ticket.device_id:
            # Try to match device from user's response
            matched_device = None
            user_input = user_msg.lower().strip()
            
            for device in user_devices:
                # Match by partial token or full name
                dev_lower = device.lower()
                dev_tokens = [t for t in dev_lower.replace('/', ' ').split() if t and len(t) > 2]
                
                if dev_lower in user_input or user_input in dev_lower:
                    matched_device = device
                    break
                for token in dev_tokens:
                    if token in user_input:
                        matched_device = device
                        break
                if matched_device:
                    break
            
            if matched_device:
                ticket = ticket.model_copy(update={"device_id": matched_device})
                print(f"[TicketAgent] Device validated: {matched_device}")
            else:
                # No match found - ask again with validation message
                print(f"[TicketAgent] Invalid device input: '{user_msg}' - asking again")
                return ticket, "device_retry", extra_idx
            
            return ticket, None, extra_idx
        
        # Priority selection with validation
        if last_question == "priority" and not ticket.priority:
            priority_map = {
                "low": "Low", "1": "Low", "l": "Low",
                "medium": "Medium", "2": "Medium", "m": "Medium", "med": "Medium",
                "high": "High", "3": "High", "h": "High",
                "critical": "Critical", "4": "Critical", "c": "Critical", "crit": "Critical"
            }
            user_input = user_msg.lower().strip()
            matched = priority_map.get(user_input)
            
            if matched:
                ticket = ticket.model_copy(update={"priority": matched})
                print(f"[TicketAgent] Priority validated: {matched}")
            else:
                # Try partial match
                for key, val in priority_map.items():
                    if key in user_input:
                        ticket = ticket.model_copy(update={"priority": val})
                        print(f"[TicketAgent] Priority matched from partial: {val}")
                        break
                
                if not ticket.priority:
                    # Still no match - ask again
                    print(f"[TicketAgent] Invalid priority input: '{user_msg}' - asking again")
                    return ticket, "priority_retry", extra_idx
            
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
    
    def _auto_fill_fields(self, ticket, user_info, detected_cat, messages, user_devices):
        """Auto-fill fields from context - ONLY when user explicitly mentions them"""
        # User info
        if not ticket.user_id and user_info:
            ticket = ticket.model_copy(update={
                "user_id": user_info.get("user_id"),
                "user_name": user_info.get("user_name"),
                "email": user_info.get("email"),
                "phone": user_info.get("phone"),
                "department": user_info.get("department")
            })
        
        # Issue summary - extract from user's original issue description
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

        # Device detection: ONLY from user's issue description messages (HumanMessage)
        # Look for EXPLICIT device mentions like "my Dell laptop" or "MacBook"
        try:
            if not ticket.device_id and user_devices:
                # Only check HumanMessages that describe the issue (not confirmations like "yes")
                issue_messages = []
                for m in messages:
                    if isinstance(m, HumanMessage):
                        content = m.content.lower()
                        # Skip short confirmations
                        if len(content) > 10 and content not in ['yes', 'no', 'ok', 'okay']:
                            issue_messages.append(content)
                
                issue_text = " ".join(issue_messages)
                
                # Only match if user explicitly mentions a device with context words
                device_context_words = ['my', 'on', 'using', 'with', 'the', 'this']
                for device in user_devices:
                    dev_lower = device.lower()
                    # Get significant tokens (skip generic words)
                    significant_tokens = [t for t in dev_lower.replace('/', ' ').split() 
                                        if t and len(t) > 2 and t not in ['pro', 'the']]
                    
                    # Check if device name appears with context
                    for token in significant_tokens:
                        if token in issue_text:
                            # Verify it's in a device-mentioning context
                            for ctx in device_context_words:
                                if f"{ctx} {token}" in issue_text or f"{token}" in issue_text:
                                    # Double-check: token should be a device identifier, not a common word
                                    if token in ['dell', 'hp', 'macbook', 'ipad', 'iphone', 'latitude', 'printer', 'laserjet']:
                                        ticket = ticket.model_copy(update={"device_id": device})
                                        print(f"[TicketAgent] Auto-detected device: {device}")
                                        break
                    if ticket.device_id:
                        break
        except Exception as e:
            print(f"[TicketAgent] Device detection error: {e}")

        # Priority detection: ONLY from explicit urgency indicators in user's issue description
        try:
            if not ticket.priority:
                # Only check HumanMessages that describe the issue
                issue_messages = [m.content.lower() for m in messages 
                                 if isinstance(m, HumanMessage) and len(m.content) > 10]
                issue_text = " ".join(issue_messages)
                
                # Priority keywords with context - must be explicit
                priority_phrases = {
                    "Critical": ["system down", "completely down", "not working at all", "emergency", "critical"],
                    "High": ["very urgent", "urgently", "asap", "blocking my work", "can't work", "blocking work", "please help"],
                    "Medium": ["affecting work", "need help", "important"],
                    # Don't auto-fill Low - let user choose
                }
                
                for priority, phrases in priority_phrases.items():
                    for phrase in phrases:
                        if phrase in issue_text:
                            ticket = ticket.model_copy(update={"priority": priority})
                            print(f"[TicketAgent] Auto-detected priority: {priority} (phrase: {phrase})")
                            break
                    if ticket.priority:
                        break
        except Exception as e:
            print(f"[TicketAgent] Priority detection error: {e}")

        return ticket
    
    def _ask_next_field(self, ticket, user_devices, extra_idx, state):
        """Ask for next missing field with validation"""
        last_question = state.get("last_question")
        
        # Handle device retry (validation failed)
        if last_question == "device_retry":
            device_list = "\n".join([f"  • {d}" for d in user_devices])
            msg = f"⚠️ I couldn't find that device. Please select from your registered devices:\n\n{device_list}"
            return {
                "messages": [AIMessage(content=msg)],
                "ticket": ticket,
                "last_question": "device",
                "current_extra_field_index": extra_idx
            }
        
        # Handle priority retry (validation failed)
        if last_question == "priority_retry":
            msg = """⚠️ Please choose a valid priority level:

  • **Low** (1) - Can wait
  • **Medium** (2) - Affecting work
  • **High** (3) - Blocking work
  • **Critical** (4) - System down

Type: Low, Medium, High, or Critical"""
            return {
                "messages": [AIMessage(content=msg)],
                "ticket": ticket,
                "last_question": "priority",
                "current_extra_field_index": extra_idx
            }
        
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
        
        # Description - AUTO-GENERATE from conversation (Smart Summarization)
        if not ticket.description:
            # Generate AI summary of the troubleshooting conversation
            ai_description = self._generate_conversation_summary(state.get("messages", []), ticket)
            ticket = ticket.model_copy(update={"description": ai_description})
            print(f"[TicketAgent] Auto-generated description from conversation")
        
        # All done - ready for preview
        return {
            "messages": [AIMessage(content="Perfect! Let me show you the ticket preview...")],
            "ticket": ticket,
            "last_question": None,
            "current_extra_field_index": 0,
            "ticket_collection_complete": True
        }
    
    def _generate_conversation_summary(self, messages: List, ticket) -> str:
        """Generate an AI summary of the troubleshooting conversation for ticket description"""
        try:
            # Extract relevant conversation parts (skip system messages and short confirmations)
            conversation_parts = []
            for m in messages:
                if isinstance(m, HumanMessage):
                    if len(m.content) > 5:  # Skip very short responses
                        conversation_parts.append(f"User: {m.content}")
                elif isinstance(m, AIMessage):
                    # Skip ticket form prompts and confirmations
                    if not any(skip in m.content for skip in [
                        "What category", "Which device", "Priority level", 
                        "Type 'no' to skip", "Ticket Preview", "submit", "edit", "cancel",
                        "HANDOFF_TO_TICKET_AGENT", "support ticket"
                    ]):
                        # Truncate long solutions
                        content = m.content[:500] + "..." if len(m.content) > 500 else m.content
                        conversation_parts.append(f"Support: {content}")
            
            if not conversation_parts:
                return "User reported an issue requiring IT support."
            
            conversation_text = "\n".join(conversation_parts[-10:])  # Last 10 relevant messages
            
            summary_prompt = f"""Summarize this IT support conversation into a concise ticket description.
        Include: the problem reported, troubleshooting steps attempted, and outcome.
        Keep it professional and under 50 words.

        Issue Summary: {ticket.issue_summary or 'Not specified'}
        Category: {ticket.category or 'General'}

        CONVERSATION:
        {conversation_text}

        Write a clear, professional description for the IT support ticket:"""
            
            response = self.llm.invoke([SystemMessage(content=summary_prompt)])
            summary = response.content.strip()
            
            # Fallback if summary is too short or empty
            if len(summary) < 20:
                return f"User reported: {ticket.issue_summary or 'IT issue'}. Troubleshooting was attempted but issue persists."
            
            return summary
            
        except Exception as e:
            print(f"[TicketAgent] Summary generation error: {e}")
            return f"User reported: {ticket.issue_summary or 'IT issue'}. Requires IT support assistance."


# Global agent instances
chatbot_agent = ChatbotAgent()
ticket_agent = TicketAgent()


def get_chatbot_agent() -> ChatbotAgent:
    """Get the global chatbot agent instance"""
    return chatbot_agent


def get_ticket_agent() -> TicketAgent:
    """Get the global ticket agent instance"""
    return ticket_agent
