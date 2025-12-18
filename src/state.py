from typing import TypedDict, Annotated, List, Optional, Dict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
import uuid
from datetime import datetime

# =============================================================================
# CATEGORY-SPECIFIC FORM TEMPLATES
# =============================================================================
# Each category has different fields based on what information is needed

FORM_TEMPLATES = {
    "Network": {
        "name": "Network Issue",
        "extra_fields": ["connection_type", "error_message"],
        "field_prompts": {
            "connection_type": "What type of connection are you having issues with?\n  • WiFi\n  • Ethernet/Wired\n  • VPN",
            "error_message": "Are you seeing any error messages? (Type 'no' if none)"
        }
    },
    "Account": {
        "name": "Account/Login Issue",
        "extra_fields": ["account_type", "last_working"],
        "field_prompts": {
            "account_type": "What type of account is affected?\n  • Windows/Computer Login\n  • Email\n  • VPN\n  • Application (specify which)",
            "last_working": "When did it last work correctly? (e.g., 'yesterday', '2 days ago')"
        }
    },
    "Hardware": {
        "name": "Hardware Issue",
        "extra_fields": ["component", "physical_damage"],
        "field_prompts": {
            "component": "Which hardware component is affected?\n  • Display/Monitor\n  • Keyboard/Mouse\n  • Battery\n  • Audio/Speakers\n  • Other",
            "physical_damage": "Is there any visible physical damage? (yes/no)"
        }
    },
    "Software": {
        "name": "Software Issue",
        "extra_fields": ["application_name", "error_code"],
        "field_prompts": {
            "application_name": "What is the name of the application having issues?",
            "error_code": "Any error codes or messages? (Type 'no' if none)"
        }
    },
    "Email": {
        "name": "Email Issue",
        "extra_fields": ["email_client", "affected_action"],
        "field_prompts": {
            "email_client": "Which email application are you using?\n  • Outlook Desktop\n  • Outlook Web\n  • Mobile App\n  • Other",
            "affected_action": "What action is not working?\n  • Sending emails\n  • Receiving emails\n  • Both\n  • Other (calendar, contacts, etc.)"
        }
    },
    "General": {
        "name": "General IT Issue",
        "extra_fields": [],
        "field_prompts": {}
    }
}


# =============================================================================
# TICKET SCHEMA - Core ticket fields all categories share
# =============================================================================
class TicketSchema(BaseModel):
    """IT Support Ticket Schema with all required fields"""
    
    # Auto-generated fields
    ticket_id: Optional[str] = Field(None, description="Unique ticket identifier")
    created_at: Optional[str] = Field(None, description="Timestamp when ticket was created")
    
    # User information (would come from login session in production)
    user_id: Optional[str] = Field(None, description="Employee/User ID")
    user_name: Optional[str] = Field(None, description="Full name of the user")
    email: Optional[str] = Field(None, description="User's email address")
    phone: Optional[str] = Field(None, description="Contact phone number")
    department: Optional[str] = Field(None, description="User's department")
    
    # Issue classification
    category: Optional[str] = Field(None, description="Issue category: Network, Account, Hardware, Software, Email, General")
    
    # Core ticket fields (collected from user)
    issue_summary: Optional[str] = Field(None, description="Short summary of the issue")
    device_id: Optional[str] = Field(None, description="The specific device affected")
    priority: Optional[str] = Field(None, description="Priority: Low, Medium, High, Critical")
    description: Optional[str] = Field(None, description="Detailed description of the problem")
    
    # Category-specific extra fields (stored as dict)
    extra_fields: Optional[Dict[str, str]] = Field(default_factory=dict, description="Category-specific additional fields")


def create_empty_ticket() -> dict:
    """Create an empty ticket dict with all fields initialized"""
    return {
        "ticket_id": None,
        "created_at": None,
        "user_id": None,
        "user_name": None,
        "email": None,
        "phone": None,
        "department": None,
        "category": None,
        "issue_summary": None,
        "device_id": None,
        "priority": None,
        "description": None,
        "extra_fields": {}
    }


def generate_ticket_id() -> str:
    """Generate a unique ticket ID"""
    return f"TKT-{uuid.uuid4().hex[:8].upper()}"


# =============================================================================
# AGENT STATE - The main state structure for the workflow
# =============================================================================
class AgentState(TypedDict):
    # Conversation history
    messages: Annotated[List, add_messages]
    # active_agent: Optional[str] # "chatbot" or "ticket"
    
    # Current ticket being created/edited
    ticket: TicketSchema
    
    # User context (simulated - would come from login session)
    user_info: Dict[str, str]  # {user_id, user_name, email, phone, department}
    user_devices: List[str]
    
    # KB metadata
    kb_used: Optional[bool]
    kb_confidence: Optional[str]
    detected_category: Optional[str]
    
    # Workflow state tracking
    ticket_preview_shown: Optional[bool]
    awaiting_confirmation: Optional[bool]
    awaiting_ticket_confirmation: Optional[bool]  # Waiting for user to confirm they want to create a ticket
    last_question: Optional[str]  # Current field being asked
    confirmation_action: Optional[str]
    
    # Category-specific form tracking
    current_extra_field_index: Optional[int]  # Which extra field we're currently asking about
    
    # Multi-agent tracking
    current_agent: Optional[str]  # "chatbot" or "ticket"
    ticket_collection_complete: Optional[bool]  # Flag when all ticket fields collected
