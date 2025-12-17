from typing import TypedDict, Annotated, List, Optional
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

# 1. The Ticket Structure (as per your requirements)
class TicketSchema(BaseModel):
    issue_summary: Optional[str] = Field(None, description="Short summary of the issue")
    device_id: Optional[str] = Field(None, description="The specific device")
    priority: Optional[str] = Field(None, description="Severity: Low, Medium, High")
    description: Optional[str] = Field(None, description="Detailed description of the problem")
    # is_complete: bool = False

# 2. The Graph State
class AgentState(TypedDict):
    # 'messages' tracks the entire conversation
    messages: Annotated[List, add_messages]
    
    # 'ticket' holds the data extracted so far
    ticket: TicketSchema
    
    # 'user_info' would come from the login session (Simulated here)
    user_devices: List[str]

    # KB metadata (not the KB object itself - that's not serializable)
    kb_used: Optional[bool]  # Whether KB was consulted
    kb_confidence: Optional[str]  # Confidence level of KB results
    detected_category: Optional[str]  # Auto-detected issue category

    ticket_preview_shown: Optional[bool]  # Track if preview was shown
    awaiting_confirmation: Optional[bool]  # Waiting for user to confirm ticket
    last_question: Optional[str]  # Track what question we just asked (device/priority/description)