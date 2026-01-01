"""
Multi-Agent System for IT Support
- ChatbotAgent: Handles troubleshooting and KB queries
- TicketAgent: Handles ticket creation and management

Industry-Standard Features:
- LLM-based semantic entity extraction (replaces hardcoded phrase matching)
- Structured output for deterministic handoff (replaces regex string matching)
- Proper exception handling with logging
"""

import logging
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, List
from src.state import (
    AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket,
    ExtractedTicketFields, ChatbotResponseAction
)
from src.kb import get_global_kb, get_best_solution, detect_category
from src.prompts import PromptBuilder
from src.validators import ExtractionValidator, validate_extraction_result
from src.constants import (
    VALID_CATEGORIES, VALID_PRIORITIES, 
    AFFIRMATIVE_WORDS, NEGATIVE_WORDS,
    FIELD_CONFIDENCE_THRESHOLDS, DEFAULT_CONFIDENCE_THRESHOLD
)
import os
from dotenv import load_dotenv
load_dotenv()

# Setup logging
logger = logging.getLogger(__name__)

# Initialize LLM with exception handling
try:
    llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)
except Exception as e:
    logger.error(f"Failed to initialize LLM: {e}")
    raise


# =============================================================================
# AGENT 1: CHATBOT AGENT - Troubleshooting & KB Search
# =============================================================================

class ChatbotAgent:
    """
    Specialized agent for IT troubleshooting using knowledge base
    Responsibilities:
    - Search KB for solutions
    - Provide troubleshooting steps
    - Detect when user needs ticket escalation (via structured output)
    
    Industry-Standard Features:
    - Uses structured output (ChatbotResponseAction) for deterministic handoff
    - No fragile string matching for escalation detection
    - Proper exception handling
    """
    
    def __init__(self):
        self.name = "Chatbot Agent"
        try:
            self.llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)
            # LLM with structured output for deterministic handoff decisions
            self.structured_llm = self.llm.with_structured_output(ChatbotResponseAction)
        except Exception as e:
            logger.error(f"Failed to initialize ChatbotAgent LLM: {e}")
            raise
    
    def process(self, state: AgentState) -> Dict:
        """Main processing function for chatbot agent with exception handling"""
        try:
            messages = state.get("messages", [])
            user_message = messages[-1].content if messages else ""
            awaiting_ticket_confirmation = state.get("awaiting_ticket_confirmation", False)
        
            # Step 0: Validate IT scope (only for new user messages, not for confirmations)
            if not awaiting_ticket_confirmation and messages:
                # Check if this is a new user query (not a follow-up to existing conversation)
                # Skip scope check if we're deep in conversation (more than 2 messages)
                if len(messages) <= 2:  # First or second message
                    is_in_scope = self._check_it_scope(user_message)
                    
                    if not is_in_scope:
                        out_of_scope_msg = """I'm a general chatbot assistant that can help with conversations and IT support.

However, your request appears to be for a different service (like travel booking, food delivery, shopping, etc.) that I'm not equipped to handle.

I can help you with:
• General questions and conversation
• IT support (password issues, software problems, hardware issues)
• Network connectivity (WiFi, VPN)
• Email and account access

Feel free to ask me anything else!"""
                    
                        logger.info("Request is out of scope, declining gracefully")
                        return {
                            "messages": [AIMessage(content=out_of_scope_msg)],
                            "awaiting_ticket_confirmation": False,
                            "wants_ticket": False,
                            "detected_category": "OUT_OF_SCOPE"
                        }
        
            # Handle ticket creation confirmation
            if awaiting_ticket_confirmation:
                response_lower = user_message.lower().strip()
                
                # User confirms ticket creation - use centralized constants
                if any(word in response_lower for word in AFFIRMATIVE_WORDS):
                    msg = "I'll transfer you to our Ticket Agent to create a support ticket."
                    logger.info("User confirmed ticket creation, handing off to TicketAgent")
                    
                    # Pre-fill ticket fields using LLM extraction (instead of hardcoded matching)
                    prefill = {}
                    try:
                        user_devices = state.get("user_devices", []) or []
                        convo_text = " ".join([m.content for m in messages[-5:] if hasattr(m, 'content')])
                        
                        # CONSISTENCY FIX: Use previously detected category as a strong hint
                        # to avoid re-detection inconsistency
                        previously_detected_category = state.get("detected_category")
                        
                        # Use LLM-based extraction for semantic understanding
                        extracted = self._extract_ticket_fields(convo_text, user_devices)
                        if extracted:
                            if extracted.get("device_id"):
                                prefill["device_id"] = extracted["device_id"]
                            if extracted.get("priority"):
                                prefill["priority"] = extracted["priority"]
                            # Use previously detected category if available, otherwise use extracted
                            if previously_detected_category and previously_detected_category != "OUT_OF_SCOPE":
                                prefill["category"] = previously_detected_category
                                logger.info(f"Using previously detected category: {previously_detected_category}")
                            elif extracted.get("category"):
                                prefill["category"] = extracted["category"]
                            logger.debug(f"LLM extracted fields: {prefill}")
                    except Exception as e:
                        logger.warning(f"Field extraction error: {e}")
                        prefill = {}

                    # Merge prefill into existing ticket state
                    ticket_obj = state.get("ticket") or create_empty_ticket()
                    if isinstance(ticket_obj, dict):
                        ticket_obj.update(prefill)
                    else:
                        try:
                            ticket_obj = ticket_obj.model_copy(update=prefill)
                        except Exception:
                            pass

                    return {
                        "messages": [AIMessage(content=msg)],
                        "awaiting_ticket_confirmation": False,
                        "escalate_to_ticket": True,  # STRUCTURED FLAG for deterministic routing
                        "ticket": ticket_obj
                    }
                
                # User declines ticket creation - use centralized constants
                elif any(word in response_lower for word in NEGATIVE_WORDS):
                    msg = "No problem! Is there anything else I can help you with?"
                    logger.info("User declined ticket creation, staying in chatbot mode")
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
            # KB search
            kb_results = {"found": False, "solutions": [], "confidence": "low"}
            detected_cat = None
            
            if kb:
                try:
                    # Pass conversation context to LLM-based category detection
                    conversation_context = [m.content for m in messages[:-1]]
                    detected_cat = detect_category(user_message, conversation_context)
                    
                    kb_results = get_best_solution(
                        kb=kb,
                        issue_description=user_message,
                        conversation_history=conversation_context,
                        category=detected_cat
                    )
                    logger.info(f"Detected category: {detected_cat}")
                    logger.debug(f"KB found: {kb_results['found']}, confidence: {kb_results.get('confidence')}")
                except Exception as e:
                    logger.warning(f"KB search error: {e}")
            
            # Check if user is reporting solution didn't work (ambiguous feedback)
            is_ambiguous_feedback = self._is_ambiguous_feedback(user_message, messages)
            
            # Check if user EXPLICITLY wants a ticket (not just describing a problem)
            # Only match specific ticket-related phrases, NOT general problem descriptions
            wants_ticket_explicit = any(phrase in user_message.lower() for phrase in [
                "create ticket", "file ticket", "submit ticket", "open ticket", 
                "create a ticket", "file a ticket", "open a ticket",
                "escalate", "escalate this", "raise a ticket", "log a ticket"
            ])
            
            # Check if solution didn't work (user already tried KB solution)
            solution_failed = any(phrase in user_message.lower() for phrase in [
                "didn't work", "doesn't work", "didn't help", "doesn't help",
                "still broken", "still not working", "still issue", "not fixed",
                "still have the problem", "still having", "tried that", "already tried"
            ]) and len(messages) > 2  # Only if conversation has progressed
            
            logger.debug(f"Ambiguous feedback: {is_ambiguous_feedback}, Wants ticket: {wants_ticket_explicit}, Solution failed: {solution_failed}")
            
            # ✅ CRITICAL: Don't offer ticket if request is OUT_OF_SCOPE
            if detected_cat == "OUT_OF_SCOPE":
                msg = """I appreciate you wanting to create a ticket, but your request appears to be outside IT support scope.

I can help with IT issues like password resets, software problems, hardware issues, and network connectivity.

For other requests, please contact the appropriate department.
Is there any IT support I can help you with?"""
                logger.info("Request is OUT_OF_SCOPE, not offering ticket")
                return {
                    "messages": [AIMessage(content=msg)],
                    "detected_category": detected_cat,
                    "awaiting_ticket_confirmation": False
                }
            
            # If user gives ambiguous feedback, explicitly wants ticket, OR solution failed -> ASK
            if is_ambiguous_feedback or wants_ticket_explicit or solution_failed:
                msg = "Would you like me to create a support ticket for this issue? (yes/no)"
                logger.info("Asking user for ticket confirmation")
                return {
                    "messages": [AIMessage(content=msg)],
                    "detected_category": detected_cat,
                    "awaiting_ticket_confirmation": True
                }
            
            # Build system prompt using centralized PromptBuilder
            if kb_results["found"] and kb_results["confidence"] in ["high", "medium"]:
                kb_context = "\n\n".join([
                    f"**Solution** (Relevance: {sol['similarity']:.0%}):\n{sol['content']}"
                    for sol in kb_results["solutions"][:2]
                ])
                system_prompt = PromptBuilder.build_chatbot_system_prompt(kb_context=kb_context)
            else:
                system_prompt = PromptBuilder.build_chatbot_system_prompt(kb_context=None)
            
            response = self.llm.invoke([SystemMessage(content=system_prompt)] + messages)
            
            return {
                "messages": [response],
                "detected_category": detected_cat,
                "kb_used": kb_results["found"],
                "kb_confidence": kb_results.get("confidence", "none")
            }
        
        except Exception as e:
            logger.error(f"Error in ChatbotAgent.process: {e}", exc_info=True)
            # Return a graceful error response
            return {
                "messages": [AIMessage(content="I apologize, but I encountered an error processing your request. Please try again.")],
                "detected_category": None,
                "kb_used": False,
                "kb_confidence": "none"
            }
    
    def _check_it_scope(self, user_message: str) -> bool:
        """
        Validate if the user request is clearly in OTHER domains (not IT or general conversation).
        Returns True if the request should be processed, False if it's clearly other-domain.
        
        This is a GENERAL CHATBOT with IT support capabilities, so we should:
        - ALLOW: General conversation, greetings, unclear requests, IT questions
        - REJECT: Only clearly other-domain requests (travel, food, shopping, etc.)
        """
        system_prompt = """You are a domain classifier for a general-purpose chatbot with IT support capabilities.

This chatbot CAN handle:
- General conversation (greetings, small talk, questions)
- IT support (password resets, software issues, hardware problems, network, email)
- Unclear or ambiguous requests (give benefit of the doubt)
- Creating IT SUPPORT TICKETS (file a ticket, create ticket, etc.)

This chatbot should ONLY REJECT requests that are clearly in OTHER SPECIFIC DOMAINS:
- Travel and transportation (booking flights, trains, buses, taxis, hotels)
- Food services (ordering pizza, restaurant reservations, food delivery)
- Shopping and e-commerce (buying products, tracking packages)
- Entertainment bookings (movie tickets, concert tickets, event tickets)
- Professional services (doctor appointments, legal advice, financial services)

CRITICAL DISAMBIGUATION:
- "book a ticket for my laptop" → IT SUPPORT (laptop = IT device, means create support ticket) → YES
- "book a ticket to Paris" → TRAVEL (destination = travel intent) → NO
- "file a ticket for London" → TRAVEL (trip = travel intent) → NO
- "file a ticket for my computer issue" → IT SUPPORT (computer = IT device) → YES
- "file a ticket" → IT SUPPORT (IT context) → YES
- "create ticket" → IT SUPPORT (IT context) → YES
- "book flight" → TRAVEL → NO
- "order pizza" → FOOD → NO

IMPORTANT RULES:
- If message mentions IT devices (laptop, computer, WiFi, software) → ALLOW (respond "YES")
- Greetings and casual conversation → ALLOW (respond "YES")
- Unclear or ambiguous requests → ALLOW (respond "YES")
- IT support questions → ALLOW (respond "YES")
- General questions → ALLOW (respond "YES")
- ONLY clearly other-domain service requests → REJECT (respond "NO")

Analyze the user's message and respond with ONLY one word:
- "YES" if it should be processed (general chat OR IT support)
- "NO" ONLY if it's clearly a request for OTHER domain services (travel, food, shopping, etc.)

When in doubt, respond "YES"."""
        
        try:
            response = self.llm.invoke([
                SystemMessage(content=system_prompt),
                HumanMessage(content=f"User request: {user_message}")
            ])
            
            result = response.content.strip().upper()
            is_it_related = "YES" in result
            
            logger.info(f"[ChatbotAgent] Scope check: '{user_message[:50]}...' -> {result} (IT-related: {is_it_related})")
            return is_it_related
            
        except Exception as e:
            logger.warning(f"[ChatbotAgent] Scope check error: {e}, defaulting to True")
            # On error, default to allowing the request (fail-open)
            return True
    
    def _extract_ticket_fields(self, conversation_text: str, user_devices: List[str]) -> Dict:
        """
        LLM-based semantic extraction of ticket fields.
        
        INDUSTRY-STANDARD APPROACH:
        - Uses structured output with Pydantic schema
        - Semantic understanding instead of brittle phrase matching
        - Handles synonyms, typos, and natural language variations
        - e.g., "This box is toast" → Hardware/Critical
        
        Args:
            conversation_text: Recent conversation context
            user_devices: List of user's registered devices
        
        Returns:
            Dict with extracted fields: device_id, priority, category
        """
        try:
            # Build extraction LLM with structured output
            extraction_llm = self.llm.with_structured_output(ExtractedTicketFields)
            
            # Use centralized prompt builder
            devices_context = PromptBuilder.format_devices_list(user_devices)
            extraction_prompt = PromptBuilder.build_extraction_prompt(
                devices_context=devices_context,
                text_content=conversation_text,
                include_category=True
            )
            
            result = extraction_llm.invoke([
                SystemMessage(content=extraction_prompt)
            ])
            
            extracted = {}
            
            # Map and validate priority using centralized validator
            if result.priority:
                validated_priority = ExtractionValidator.validate_priority(result.priority)
                if validated_priority:
                    extracted["priority"] = validated_priority
                else:
                    logger.warning(f"[ChatbotAgent] Invalid priority discarded: {result.priority}")
            
            # Map and validate category using centralized validator
            if result.category:
                validated_category = ExtractionValidator.validate_category(result.category)
                if validated_category:
                    extracted["category"] = validated_category
                else:
                    logger.warning(f"[ChatbotAgent] Invalid category discarded: {result.category}")
            
            # Match device using LLM intelligence (avoids buggy string matching)
            # ONLY match if user explicitly mentioned a brand (avoid ambiguous guessing)
            if user_devices and result.device_brand:
                # Use centralized device matching prompt
                device_match_prompt = PromptBuilder.build_device_match_prompt(
                    device_brand=result.device_brand or '',
                    device_type=result.device_type or '',
                    user_devices=user_devices
                )
                
                try:
                    match_result = self.llm.invoke([SystemMessage(content=device_match_prompt)])
                    matched_device = match_result.content.strip()
                    
                    # Validate using centralized validator
                    validated_device = ExtractionValidator.validate_device(matched_device, user_devices)
                    if validated_device:
                        extracted["device_id"] = validated_device
                        logger.info(f"[ChatbotAgent] LLM matched device: '{validated_device}'")
                except Exception as e:
                    logger.warning(f"[ChatbotAgent] Device matching error: {e}")
            
            logger.info(f"[ChatbotAgent] LLM extraction result: priority={result.priority}, category={result.category}, device_brand={result.device_brand}, device_type={result.device_type}")
            return extracted
            
        except Exception as e:
            logger.warning(f"[ChatbotAgent] LLM extraction error: {e}")
            return {}
    
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
        try:
            self.llm = ChatOpenAI(model="gpt-4.1-mini", temperature=0)
            self.llm_with_tools = self.llm.bind_tools([TicketSchema])
        except Exception as e:
            logger.error(f"Failed to initialize TicketAgent LLM: {e}")
            raise
    
    def process_ticket_collection(self, state: AgentState) -> Dict:
        """Collect ticket information step by step or handle edits with exception handling"""
        try:
            current_ticket = state.get("ticket", {})
            if isinstance(current_ticket, dict):
                current_ticket = TicketSchema(**current_ticket)

            messages = state.get("messages", [])
            
            # Get the last HUMAN message (not AI message)
            last_user_message = ""
            for m in reversed(messages):
                if isinstance(m, HumanMessage):
                    last_user_message = m.content
                    break

            # Check if we're in edit mode (user said "edit" and now providing what to change)
            is_edit_mode = state.get("edit_mode", False)
            
            if is_edit_mode:
                logger.info(f"Processing edit request: {last_user_message}")
                
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
Map priority to:
- "low", "l", "1" → use EXACT value: "Low"
- "medium", "med", "m", "2" → use EXACT value: "Medium"
- "high", "h", "3" → use EXACT value: "High"
- "critical", "crit", "c", "4" → use EXACT value: "Critical"

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
                    logger.info(f"[TicketAgent] Extracted changes: {new_data}")
                    updated_ticket = current_ticket.model_copy(update=new_data)
                else:
                    logger.info(f"[TicketAgent] No changes extracted from: {last_user_message}")
                
                # Return to preview with updated ticket, exit edit mode
                return {
                    "messages": [AIMessage(content="I've updated the ticket. Here's the revised preview...")],
                    "ticket": updated_ticket,
                    "edit_mode": False,
                    "confirmation_action": None,
                    "ticket_collection_complete": True  # Go to preview
                }

            # --- Normal Ticket Collection Logic ---
            user_devices = state.get("user_devices", [])
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

            if not updated_ticket.device_id and user_devices and len(user_devices) == 1:
                # Auto-select the only available device
                single_device = user_devices[0]
                updated_ticket = updated_ticket.model_copy(update={"device_id": single_device})
                logger.info(f"Auto-selected single device: {single_device}")
            
            # Check for missing fields and ask next question
            return self._ask_next_field(updated_ticket, user_devices, new_extra_index, state)
        
        except Exception as e:
            logger.error(f"Error in TicketAgent.process_ticket_collection: {e}", exc_info=True)
            return {
                "messages": [AIMessage(content="I apologize, but I encountered an error processing your ticket information. Please try again.")],
                "ticket": state.get("ticket", create_empty_ticket()),
            }
    
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
            
            # Collect all potential matches with their match quality scores
            candidates = []
            
            for device in user_devices:
                dev_lower = device.lower()
                
                # Priority 1: Exact match (case-insensitive)
                if dev_lower == user_input or user_input == dev_lower:
                    candidates.append((device, 1000))  # Highest priority
                    continue
                
                # Priority 2: Full device name contained in input
                elif dev_lower in user_input:
                    candidates.append((device, 500 + len(dev_lower)))  # Prefer longer matches
                    continue
                
                # Priority 3: Input contained in device name
                elif user_input in dev_lower:
                    candidates.append((device, 400 + len(user_input)))
                    continue
                
                # Priority 4: Token-based matching (lowest priority)
                dev_tokens = [t for t in dev_lower.replace('/', ' ').split() if t and len(t) > 2]
                for token in dev_tokens:
                    if token in user_input:
                        # Score based on token length to prefer more specific matches
                        candidates.append((device, len(token)))
                        break
            
            # Select the best match (highest score)
            if candidates:
                matched_device = max(candidates, key=lambda x: x[1])[0]
                ticket = ticket.model_copy(update={"device_id": matched_device})
                logger.info(f"[TicketAgent] Device validated: {matched_device}")
            else:
                # No match found - ask again with validation message
                logger.info(f"[TicketAgent] Invalid device input: '{user_msg}' - asking again")
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
                logger.info(f"[TicketAgent] Priority validated: {matched}")
            else:
                # Try partial match
                for key, val in priority_map.items():
                    if key in user_input:
                        ticket = ticket.model_copy(update={"priority": val})
                        logger.info(f"[TicketAgent] Priority matched from partial: {val}")
                        break
                
                if not ticket.priority:
                    # Still no match - ask again
                    logger.info(f"[TicketAgent] Invalid priority input: '{user_msg}' - asking again")
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
        """
        Auto-fill fields from context using LLM-based semantic extraction.
        
        INDUSTRY-STANDARD APPROACH:
        - Uses LLM with Pydantic schema for semantic understanding
        - Replaces brittle hardcoded phrase lists
        - Handles synonyms, natural language, and edge cases
        - e.g., "This box is toast" → Hardware/Critical
        """
        # User info (deterministic - no LLM needed)
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
            # Use centralized prompt builder for consistency
            summary_prompt = PromptBuilder.build_issue_summary_prompt()
            response = self.llm_with_tools.invoke([SystemMessage(content=summary_prompt)] + messages)
            if response.tool_calls:
                new_data = response.tool_calls[0]['args']
                if 'issue_summary' in new_data:
                    ticket = ticket.model_copy(update={'issue_summary': new_data['issue_summary']})
        
        # Category
        if not ticket.category and detected_cat:
            ticket = ticket.model_copy(update={"category": detected_cat})

        # =====================================================================
        # LLM-BASED SEMANTIC EXTRACTION (Industry Standard)
        # Replaces brittle hardcoded phrase matching
        # =====================================================================
        try:
            # Only extract if we have missing fields
            needs_device = not ticket.device_id and user_devices
            needs_priority = not ticket.priority
            
            if needs_device or needs_priority:
                # Collect issue description from human messages
                issue_messages = [m.content for m in messages 
                                 if isinstance(m, HumanMessage) and len(m.content) > 10]
                issue_text = " ".join(issue_messages)
                
                if issue_text:
                    # Use LLM-based extraction
                    extracted = self._llm_extract_fields(issue_text, user_devices)
                    
                    if needs_device and extracted.get("device_id"):
                        ticket = ticket.model_copy(update={"device_id": extracted["device_id"]})
                        logger.info(f"[TicketAgent] LLM auto-detected device: {extracted['device_id']}")
                    
                    if needs_priority and extracted.get("priority"):
                        ticket = ticket.model_copy(update={"priority": extracted["priority"]})
                        logger.info(f"[TicketAgent] LLM auto-detected priority: {extracted['priority']}")
                        
        except Exception as e:
            logger.warning(f"[TicketAgent] LLM extraction error: {e}")

        return ticket
    
    def _llm_extract_fields(self, issue_text: str, user_devices: List[str]) -> Dict:
        """
        LLM-based semantic extraction of ticket fields.
        
        This replaces the brittle hardcoded phrase matching with semantic understanding.
        Examples of what this can now handle:
        - "This box is toast" → Hardware, Critical
        - "My laptop is being a pain" → Hardware, Medium
        - "Everything is on fire" → Critical
        - "Can't access anything" → Critical
        
        Args:
            issue_text: Combined text from user's issue descriptions
            user_devices: List of user's registered devices
        
        Returns:
            Dict with 'device_id' and 'priority' if detected
        """
        try:
            extraction_llm = self.llm.with_structured_output(ExtractedTicketFields)
            logger.debug(f"Issue text for extraction: {issue_text}")
            
            # Use centralized prompt builder (no category - already detected)
            devices_context = PromptBuilder.format_devices_list(user_devices)
            extraction_prompt = PromptBuilder.build_extraction_prompt(
                devices_context=devices_context,
                text_content=issue_text,
                include_category=False  # Category already detected by ChatbotAgent
            )
            
            result = extraction_llm.invoke([SystemMessage(content=extraction_prompt)])
            
            extracted = {}
            
            # Map and validate priority using centralized validator
            confidence_threshold = FIELD_CONFIDENCE_THRESHOLDS.get("priority", DEFAULT_CONFIDENCE_THRESHOLD)
            if result.priority and result.confidence >= confidence_threshold:
                validated_priority = ExtractionValidator.validate_priority(result.priority)
                if validated_priority:
                    extracted["priority"] = validated_priority
                else:
                    logger.warning(f"[TicketAgent] Invalid priority discarded: {result.priority}")
            
            # Match device using centralized prompt and validator
            if user_devices and result.device_brand:
                logger.info(f"[TicketAgent] LLM extracted device_brand: {result.device_brand}, device_type: {result.device_type}")
                
                device_match_prompt = PromptBuilder.build_device_match_prompt(
                    device_brand=result.device_brand or '',
                    device_type=result.device_type or '',
                    user_devices=user_devices
                )
                
                try:
                    match_result = self.llm.invoke([SystemMessage(content=device_match_prompt)])
                    matched_device = match_result.content.strip()
                    
                    # Validate using centralized validator
                    validated_device = ExtractionValidator.validate_device(matched_device, user_devices)
                    if validated_device:
                        extracted["device_id"] = validated_device
                        logger.info(f"[TicketAgent] LLM matched device: '{validated_device}'")
                except Exception as e:
                    logger.warning(f"[TicketAgent] Device matching error: {e}")
            
            logger.info(f"[TicketAgent] LLM extraction: priority={result.priority}, device_brand={result.device_brand}, device_type={result.device_type}, confidence={result.confidence}")
            return extracted
            
        except Exception as e:
            logger.warning(f"[TicketAgent] LLM extraction error: {e}")
            return {}
    
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
            logger.info(f"[TicketAgent] Auto-generated description from conversation")
        
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
                        "HANDOFF_TO_TICKET_AGENT"
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

        CRITICAL RULES:
        - ONLY include information explicitly stated in the conversation
        - DO NOT invent or assume troubleshooting steps that didn't happen
        - DO NOT fabricate technical details
        - Do not mention device brand/model into the description only mention device type if mentioned

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
            logger.warning(f"[TicketAgent] Summary generation error: {e}")
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
