"""
Centralized Prompt Templates for IT Support System
All LLM prompts in one place for consistency and maintainability
"""

from typing import List, Optional
from src.constants import VALID_CATEGORIES, VALID_PRIORITIES


class PromptBuilder:
    """Builds consistent prompts for field extraction and routing"""
    
    @staticmethod
    def format_devices_list(user_devices: List[str]) -> str:
        """Format user devices for LLM prompts"""
        if not user_devices:
            return "None available"
        return "\n".join([f"  - {device}" for device in user_devices])
    
    @staticmethod
    def build_extraction_prompt(
        devices_context: str,
        text_content: str,
        include_category: bool = True
    ) -> str:
        """
        Build unified field extraction prompt
        
        Args:
            devices_context: Formatted string of user's devices
            text_content: Conversation or issue text to extract from
            include_category: Whether to include category extraction
            
        Returns:
            Complete extraction prompt
        """
        prompt = f"""You are an expert IT support analyst. Extract ticket fields from the text.

AVAILABLE USER DEVICES:
{devices_context}

EXTRACTION RULES (DO NOT HALLUCINATE):

1. **Priority** - Infer from urgency/impact:
   - Critical: System down, cannot work at all, emergency, dead, toast
   - High: Urgent, blocking work, ASAP, stuck
   - Medium: Affecting work, annoying, need help
   - Low: Can wait, minor, not urgent

2. **Device** - STRICT RULES:
   - ONLY extract device_brand if EXPLICITLY mentioned (Dell, HP, Apple, Lenovo, etc.)
   - ONLY extract device_type if mentioned (laptop, desktop, phone, printer)
   - For generic terms like "my laptop" without brand: device_brand=None, device_type="laptop"
   - NEVER guess or infer a brand not stated"""

        if include_category:
            prompt += f"""

3. **Category** - Must be one of: {', '.join(VALID_CATEGORIES)}
   - Network: WiFi, internet, VPN, connectivity
   - Account: Login, password, MFA, access
   - Hardware: Physical device issues, slow, crashes, display, keyboard
   - Software: Application errors, installations
   - Email: Outlook, email issues
   - General: Other IT issues
   - OUT_OF_SCOPE: Non-IT requests"""

        prompt += f"""

TEXT TO ANALYZE:
{text_content}

CRITICAL: Only extract what is EXPLICITLY stated. Do not assume or infer."""
        
        return prompt
    
    @staticmethod
    def build_device_match_prompt(
        device_brand: str,
        device_type: str,
        user_devices: List[str]
    ) -> str:
        """
        Build prompt for matching extracted device to registered devices
        """
        devices_list = "\n".join([f"  - {d}" for d in user_devices])
        
        return f"""Match the user's device mention to their registered devices.

USER MENTIONED: "{device_brand or ''} {device_type or ''}"

REGISTERED DEVICES:
{devices_list}

RULES:
- Return the EXACT device name from the list that best matches
- If no reasonable match exists, return exactly: None
- Return ONLY the device name, no extra text

OUTPUT:"""
    
    @staticmethod
    def build_issue_summary_prompt() -> str:
        """Build prompt for extracting issue summary"""
        return """Extract a brief, professional issue summary (5-10 words).

RULES:
- Focus on the core issue/request
- Use present tense, professional tone
- Exclude: device brands, user names, technical jargon
- Format: Start with issue type (e.g., "Laptop power failure")

EXAMPLES:
- "My laptop won't turn on" → "Laptop power failure"
- "Can't access my email" → "Email access issue"
- "WiFi keeps disconnecting" → "Intermittent WiFi connectivity"
- "Need password reset" → "Password reset request"

Use TicketSchema tool to update ONLY issue_summary."""
    
    @staticmethod
    def build_conversation_summary_prompt(
        conversation_text: str,
        issue_summary: str = None,
        category: str = None
    ) -> str:
        """Build prompt for generating ticket description from conversation"""
        return f"""Summarize this IT support conversation into a ticket description.

RULES:
- Include: problem reported, troubleshooting attempted, outcome
- Keep under 50 words, professional tone
- ONLY include information EXPLICITLY stated
- DO NOT invent troubleshooting steps that didn't happen
- Write in past tense, third person
- Start with "User reported..."

Issue Summary: {issue_summary or 'Not specified'}
Category: {category or 'General'}

CONVERSATION:
{conversation_text}

Write a clear, professional description:"""
    
    @staticmethod
    def build_chatbot_system_prompt(kb_context: str = None) -> str:
        """
        Build chatbot response prompt
        
        Args:
            kb_context: Knowledge base solutions if available
        """
        if kb_context:
            return f"""You are a friendly IT Support Chatbot Agent.

KNOWLEDGE BASE SOLUTIONS (for reference only):
{kb_context}

CRITICAL RULES:
1. For GREETINGS (hi, hello, hey): Respond warmly like "Hello! How can I assist you today?"
2. For VAGUE queries (e.g., "laptop issue", "need help"): ASK clarifying questions
3. For SPECIFIC queries: Provide troubleshooting steps from the knowledge base

Keep responses SHORT and helpful.
DO NOT mention tickets or escalation - I handle that separately."""
        else:
            return """You are a friendly IT Support Chatbot Agent.

YOUR ROLE:
1. For GREETINGS: Respond warmly like "Hello! How can I assist you today?"
2. For IT queries: Ask clarifying questions to understand the issue
3. Be conversational and empathetic

Keep responses SHORT and helpful.
DO NOT mention tickets or escalation - I handle that separately."""
