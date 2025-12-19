"""
Streamlit UI for Ticket-Agent Chatbot
A professional IT Support interface with multi-agent system integration
"""

import streamlit as st
from langgraph.graph import StateGraph, END, START
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.state import AgentState, TicketSchema, FORM_TEMPLATES, create_empty_ticket
from src.nodes import chatbot_node, ticket_collection_node, ticket_confirmation_node, ticket_preview_node, submit_ticket_node
from src.kb import initialize_kb_with_check, set_global_kb
from langgraph.checkpoint.memory import MemorySaver
import uuid
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="OF  IT Support Chatbot",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for better styling
st.markdown("""
<style>
    /* Chat message styling with theme support */
    .stChatMessage {
        padding: 10px;
        margin: 5px 0;
        border-radius: 10px;
    }
    
    /* User message (more visible) */
    div[data-testid="stChatMessageContent"] {
        background-color: rgba(28, 131, 225, 0.1);
        padding: 12px;
        border-radius: 8px;
    }
    
    /* Make sure text is always visible */
    .stMarkdown, .stChatMessage p {
        color: inherit !important;
    }
    
    /* Button styling */
    .stButton button {
        border-radius: 8px;
        font-weight: 500;
        transition: all 0.3s ease;
        border: 2px solid transparent;
    }
    
    .stButton button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        border-color: rgba(28, 131, 225, 0.5);
    }
    
    /* Primary button (Submit) */
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    }
    
    .stButton button[kind="primary"]:hover {
        background: linear-gradient(135deg, #764ba2 0%, #667eea 100%);
    }
    
    /* Info boxes with theme support */
    .ticket-preview {
        background-color: rgba(33, 150, 243, 0.15);
        border-left: 4px solid #2196F3;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
    }
    .success-box {
        background-color: rgba(76, 175, 80, 0.15);
        border-left: 4px solid #4CAF50;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
        color: inherit;
    }
    .warning-box {
        background-color: rgba(255, 152, 0, 0.15);
        border-left: 4px solid #FF9800;
        padding: 15px;
        border-radius: 5px;
        margin: 10px 0;
        color: inherit;
    }
    
    /* Sidebar styling */
    div[data-testid="stMetricValue"] {
        font-size: 20px;
    }
    
    /* Chat input */
    .stChatInput {
        border-radius: 10px;
    }
    
    /* Loading indicator */
    .stSpinner > div {
        border-color: #1f77b4 !important;
    }
    
    /* Improve spacing in chat */
    .element-container {
        margin-bottom: 0.5rem;
    }
    
    /* Make device/category buttons more prominent */
    div[data-testid="column"] .stButton button {
        height: 3.5em;
        font-size: 0.95em;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# WORKFLOW GRAPH SETUP (Same as main.py)
# =============================================================================

def route_chatbot(state: AgentState):
    """Routes from chatbot based on state"""
    if state.get("edit_mode"):
        return "ticket_collection"
    
    if state.get("awaiting_ticket_confirmation"):
        return END
    
    if state.get("awaiting_confirmation"):
        return "ticket_confirmation"
    
    ticket_questions = ["category", "device", "priority", "description"]
    for template in FORM_TEMPLATES.values():
        ticket_questions.extend(template.get("extra_fields", []))
    
    last_question = state.get("last_question")
    if last_question in ticket_questions:
        return "ticket_collection"
    
    messages = state.get("messages", [])
    if messages:
        last_msg = messages[-1]
        if hasattr(last_msg, 'content'):
            if "HANDOFF_TO_TICKET_AGENT" in last_msg.content or "handoff_to_ticket" in last_msg.content:
                return "ticket_collection"
    
    return END


def route_ticket_collection(state: AgentState):
    """Routes from ticket collection"""
    if state.get("ticket_collection_complete"):
        return "ticket_preview"
    
    current_ticket = state.get("ticket", {})
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    has_category = current_ticket.category is not None
    has_summary = current_ticket.issue_summary is not None
    has_device = current_ticket.device_id is not None
    has_priority = current_ticket.priority is not None
    has_description = current_ticket.description is not None
    
    category = current_ticket.category or "General"
    template = FORM_TEMPLATES.get(category, FORM_TEMPLATES["General"])
    required_extras = template.get("extra_fields", [])
    current_extras = current_ticket.extra_fields or {}
    has_all_extras = all(field in current_extras for field in required_extras)
    
    if has_category and has_summary and has_device and has_priority and has_description and has_all_extras:
        return "ticket_preview"
    
    return END


def route_confirmation(state: AgentState):
    """Routes from confirmation based on user's choice"""
    action = state.get("confirmation_action", "")
    
    if action == "submit":
        return "submit_ticket"
    elif action in ["edit", "cancel"]:
        return END
    
    return END


def build_workflow():
    """Build and return the workflow graph"""
    workflow = StateGraph(AgentState)
    
    # Add nodes
    workflow.add_node("chatbot", chatbot_node)
    workflow.add_node("ticket_collection", ticket_collection_node)
    workflow.add_node("ticket_preview", ticket_preview_node)
    workflow.add_node("ticket_confirmation", ticket_confirmation_node)
    workflow.add_node("submit_ticket", submit_ticket_node)
    
    # Set entry point
    workflow.set_entry_point("chatbot")
    
    # Add edges
    workflow.add_conditional_edges(
        "chatbot",
        route_chatbot,
        {
            "ticket_collection": "ticket_collection",
            "ticket_confirmation": "ticket_confirmation",
            END: END
        }
    )
    
    workflow.add_conditional_edges(
        "ticket_collection",
        route_ticket_collection,
        {
            "ticket_preview": "ticket_preview",
            END: END
        }
    )
    
    workflow.add_edge("ticket_preview", END)
    
    workflow.add_conditional_edges(
        "ticket_confirmation",
        route_confirmation,
        {
            "submit_ticket": "submit_ticket",
            "ticket_collection": "ticket_collection",
            END: END
        }
    )
    
    workflow.add_edge("submit_ticket", END)
    
    return workflow


# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

def initialize_session_state():
    """Initialize all session state variables"""
    if "initialized" not in st.session_state:
        # User info (simulated - would come from auth in production)
        st.session_state.user_info = {
            "user_id": "EMP-12345",
            "user_name": "Krishna Ronaldo",
            "email": "krishna.ronaldo@company.com",
            "phone": "+1-777-0123",
            "department": "Engineering"
        }
        
        st.session_state.user_devices = [
            "Dell Latitude 5420",
            "iPad Pro",
            "iPhone 14",
            "MacBook Pro",
            "HP Printer LaserJet 200"
        ]
        
        # Initialize KB
        try:
            kb = initialize_kb_with_check("./chroma_db")
            set_global_kb(kb)
            st.session_state.kb_status = "✓ Connected" if kb else "⚠ Unavailable"
        except Exception as e:
            st.session_state.kb_status = f"⚠ Error: {str(e)[:30]}..."
            print(f"[KB Warning] Could not initialize KB: {e}")
        
        # Chat history
        st.session_state.messages = []
        
        # Workflow state
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.memory = MemorySaver()
        st.session_state.workflow = build_workflow()
        st.session_state.app = st.session_state.workflow.compile(
            checkpointer=st.session_state.memory
        )
        
        # Agent state tracking
        st.session_state.agent_state = {
            "user_info": st.session_state.user_info,
            "user_devices": st.session_state.user_devices,
            "ticket": create_empty_ticket(),
            "ticket_preview_shown": False,
            "awaiting_confirmation": False,
            "last_question": None,
            "current_extra_field_index": 0,
            "detected_category": None
        }
        
        # Ticket tracking
        st.session_state.current_ticket = None
        st.session_state.tickets_submitted = 0
        st.session_state.session_start = datetime.now()
        st.session_state.first_interaction = True
        st.session_state.pending_input = None
        
        st.session_state.initialized = True


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def render_message_with_buttons(content: str, message_key: str):
    """Render message content with interactive buttons if applicable"""
    
    # Check if this is a success message
    if "✅ **Ticket Created Successfully!**" in content:
        st.success("🎉 Ticket Created Successfully!")
        # Extract and display key info
        lines = content.split('\n')
        info_lines = [line for line in lines if line.strip() and '**' in line and 'Ticket ID' in line or 'Created:' in line or 'Priority:' in line or 'Category:' in line]
        for line in info_lines:
            st.markdown(line)
        st.divider()
        # Display rest of message
        remaining = '\n'.join([line for line in lines if line.strip() and not any(x in line for x in ['✅', 'Ticket ID', 'Created:', 'Priority:', 'Category:', '---'])])
        st.markdown(remaining)
        return None
    
    # Check if this is a device selection prompt
    if "Which device is affected?" in content or "couldn't find that device" in content:
        lines = content.split('\n')
        text_part = lines[0]
        devices = [line.strip().replace('• ', '') for line in lines if line.strip().startswith('•')]
        
        st.markdown(text_part)
        st.markdown("**Select a device:**")
        
        cols = st.columns(min(len(devices), 3))
        for idx, device in enumerate(devices):
            with cols[idx % 3]:
                if st.button(f"🖥️ {device}", key=f"{message_key}_device_{idx}", use_container_width=True):
                    return device
        return None
    
    # Check if this is a category selection prompt
    elif "What category best describes your issue?" in content:
        st.markdown("**What category best describes your issue?**")
        
        categories = [
            ("🌐 Network", "WiFi, Internet, VPN", "Network"),
            ("👤 Account", "Login, Password, MFA", "Account"),
            ("💻 Hardware", "Computer/Device issues", "Hardware"),
            ("📱 Software", "Application errors", "Software"),
            ("📧 Email", "Outlook, Email issues", "Email"),
            ("⚙️ General", "Other IT issues", "General")
        ]
        
        cols = st.columns(3)
        for idx, (emoji_name, desc, value) in enumerate(categories):
            with cols[idx % 3]:
                if st.button(f"{emoji_name}", key=f"{message_key}_cat_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is a priority selection prompt
    elif "Please choose a valid priority level" in content or "What is the priority" in content:
        st.markdown("**Priority Level:**")
        
        priorities = [
            ("🟢 Low", "Can wait", "Low"),
            ("🟡 Medium", "Affecting work", "Medium"),
            ("🟠 High", "Blocking work", "High"),
            ("🔴 Critical", "System down", "Critical")
        ]
        
        cols = st.columns(4)
        for idx, (emoji_name, desc, value) in enumerate(priorities):
            with cols[idx]:
                if st.button(f"{emoji_name}", key=f"{message_key}_pri_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is a ticket preview with options
    elif "📋 **Ticket Preview**" in content or "Ticket Preview" in content:
        # Extract and format ticket preview
        parts = content.split('**Options:**')
        preview_content = parts[0]
        
        # Better formatting for ticket preview
        preview_content = preview_content.replace('**--- User Information ---**', '### 👤 User Information')
        preview_content = preview_content.replace('**--- Issue Details ---**', '### 🎫 Issue Details')
        preview_content = preview_content.replace('---', '')
        
        st.markdown(preview_content)
        
        st.divider()
        st.markdown("**What would you like to do?**")
        
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ Submit Ticket", key=f"{message_key}_submit", 
                        type="primary", use_container_width=True):
                return "submit"
        with col2:
            if st.button("✏️ Edit Details", key=f"{message_key}_edit", 
                        use_container_width=True):
                return "edit"
        with col3:
            if st.button("❌ Cancel", key=f"{message_key}_cancel", 
                        use_container_width=True):
                return "cancel"
        return None
    
    # Check if this is confirmation options
    elif "Type \"submit\"" in content or "Type 'submit'" in content:
        # Extract text before options
        text_part = content.split('Type')[0].strip()
        st.markdown(text_part)
        
        st.markdown("**Options:**")
        col1, col2, col3 = st.columns(3)
        with col1:
            if st.button("✅ Submit", key=f"{message_key}_submit_opt", 
                        type="primary", use_container_width=True):
                return "submit"
        with col2:
            if st.button("✏️ Edit", key=f"{message_key}_edit_opt", 
                        use_container_width=True):
                return "edit"
        with col3:
            if st.button("❌ Cancel", key=f"{message_key}_cancel_opt", 
                        use_container_width=True):
                return "cancel"
        return None
    
    # Regular message - just display
    else:
        st.markdown(content)
        return None


def process_user_message(user_input: str):
    """Process user input through the LangGraph workflow"""
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    
    print(f"\n[UI] User input: {user_input[:100]}...")
    
    # Prepare input message
    input_message = {"messages": [HumanMessage(content=user_input)]}
    
    # On first interaction, include initial agent state
    if st.session_state.first_interaction:
        input_message.update(st.session_state.agent_state)
        st.session_state.first_interaction = False
        print("[UI] First interaction - including initial state")
    
    # Process through graph
    bot_responses = []
    try:
        for event in st.session_state.app.stream(input_message, config=config):
            for node_name, state_update in event.items():
                print(f"[UI] Node: {node_name}, Has update: {bool(state_update)}")
                
                if not state_update:
                    continue
                
                # Update agent state
                for key, value in state_update.items():
                    if key in st.session_state.agent_state:
                        st.session_state.agent_state[key] = value
                
                # Extract bot messages
                if "messages" in state_update and state_update["messages"]:
                    last_msg = state_update["messages"][-1]
                    if hasattr(last_msg, 'content') and last_msg.content:
                        content = last_msg.content
                        
                        # Filter out internal handoff signals
                        if "HANDOFF_TO_TICKET_AGENT" not in content and "handoff_to_ticket" not in content:
                            bot_responses.append(content)
                            print(f"[UI] Bot response added: {content[:100]}...")
                
                # Track ticket status
                if "ticket" in state_update and state_update["ticket"]:
                    st.session_state.current_ticket = state_update["ticket"]
                
                # Track submitted tickets
                if node_name == "submit_ticket":
                    st.session_state.tickets_submitted += 1
                    print("[UI] Ticket submitted!")
    
    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        bot_responses.append(f"⚠ Error processing message: {str(e)}")
        print(f"[UI ERROR] {error_detail}")
    
    # If no responses, add a fallback message
    if not bot_responses:
        bot_responses.append("I received your message but didn't generate a response. Could you please try rephrasing or providing more details?")
        print("[UI] No bot responses - using fallback")
    
    print(f"[UI] Total responses: {len(bot_responses)}\n")
    return bot_responses


def get_ticket_status():
    """Get current ticket creation status"""
    ticket = st.session_state.current_ticket
    if not ticket:
        return "No active ticket"
    
    try:
        if isinstance(ticket, dict):
            # Check if ticket has any meaningful data
            meaningful_data = any(
                v is not None and v != "" 
                for k, v in ticket.items() 
                if k not in ["extra_fields", "ticket_id", "created_at", "user_id", "user_name", "email", "phone", "department"]
            )
            if not meaningful_data:
                return "No active ticket"
            ticket = TicketSchema(**ticket)
        elif not isinstance(ticket, TicketSchema):
            return "No active ticket"
    except Exception:
        return "No active ticket"
    
    # Count filled fields
    filled = 0
    total = 5  # category, issue_summary, device_id, priority, description
    
    if ticket.category:
        filled += 1
    if ticket.issue_summary:
        filled += 1
    if ticket.device_id:
        filled += 1
    if ticket.priority:
        filled += 1
    if ticket.description:
        filled += 1
    
    # Add extra fields for the category
    if ticket.category:
        template = FORM_TEMPLATES.get(ticket.category, FORM_TEMPLATES["General"])
        extra_fields_needed = template.get("extra_fields", [])
        total += len(extra_fields_needed)
        
        if ticket.extra_fields:
            filled += len([f for f in extra_fields_needed if f in ticket.extra_fields])
    
    return f"In Progress ({filled}/{total} fields)"


# =============================================================================
# UI COMPONENTS
# =============================================================================

def render_sidebar():
    """Render the sidebar with user info and session stats"""
    with st.sidebar:
        st.title("🎫 IT Support")
        st.caption("Multi-Agent AI System")
        st.divider()
        
        # User Information
        st.subheader("👤 User Profile")
        user = st.session_state.user_info
        st.markdown(f"""
**{user['user_name']}**  
📧 {user['email']}  
📞 {user['phone']}  
🏢 {user['department']}  
🆔 {user['user_id']}
        """)
        
        st.divider()
        
        # Session Statistics
        st.subheader("📊 Session Stats")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Tickets Created", st.session_state.tickets_submitted)
        with col2:
            messages_count = len(st.session_state.messages)
            st.metric("Messages", messages_count)
        
        # Session duration
        duration = datetime.now() - st.session_state.session_start
        minutes = int(duration.total_seconds() / 60)
        st.metric("Session Time", f"{minutes} min")
        
        st.divider()
        
        # Current Ticket Status
        st.subheader("🎟️ Ticket Status")
        status = get_ticket_status()
        if "No active" in status:
            st.info(status)
        elif "In Progress" in status:
            st.warning(status)
        else:
            st.success(status)
        
        st.divider()
        
        # Knowledge Base Status
        st.subheader("📚 Knowledge Base")
        if "✓" in st.session_state.kb_status:
            st.success(st.session_state.kb_status)
        else:
            st.warning(st.session_state.kb_status)
        
        st.divider()
        
        # Registered Devices
        with st.expander("💻 Your Devices"):
            for device in st.session_state.user_devices:
                st.write(f"• {device}")
        
        st.divider()
        
        # Actions
        if st.button("🔄 New Session", use_container_width=True):
            # Reset session
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        # Info
        st.divider()
        st.caption("💡 **Tip:** Describe your issue and I'll help troubleshoot or create a ticket!")


def render_chat():
    """Render the main chat interface"""
    st.title("🤖 OF IT Support Chatbot")
    st.caption("Powered by Multi-Agent AI System | LangGraph + GPT-4")
    
    # Welcome message if no messages
    if not st.session_state.messages:
        st.info("""
**👋 Welcome to IT Support!**

I'm here to help with your technical issues. I can:
- 🔍 Search our knowledge base for solutions
- 🛠️ Guide you through troubleshooting steps  
- 🎫 Create support tickets if needed

**Just describe your problem to get started!**
        """)
        
        # Show KB status prominently
        if "✓" in st.session_state.kb_status:
            st.success(f"Knowledge Base: {st.session_state.kb_status}")
        else:
            st.warning(f"Knowledge Base: {st.session_state.kb_status}")
    
    # Chat messages container
    chat_container = st.container()
    
    with chat_container:
        # Display chat history
        for idx, message in enumerate(st.session_state.messages):
            role = message["role"]
            content = message["content"]
            
            with st.chat_message(role):
                # For assistant messages, check if they have interactive elements
                if role == "assistant":
                    button_response = render_message_with_buttons(content, f"msg_{idx}")
                    if button_response:
                        # User clicked a button - treat it as input
                        st.session_state.pending_input = button_response
                else:
                    st.markdown(content)
    
    # Check for pending button input
    if "pending_input" in st.session_state and st.session_state.pending_input:
        user_input = st.session_state.pending_input
        st.session_state.pending_input = None
    else:
        user_input = st.chat_input("Describe your issue or respond to questions...")
    
    if user_input:
        # Add user message to history
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # Display user message immediately
        with st.chat_message("user"):
            st.markdown(user_input)
        
        # Process through workflow with visible status
        with st.chat_message("assistant"):
            with st.status("🤔 Processing your message...", expanded=True) as status:
                st.write("🔍 Analyzing your request...")
                bot_responses = process_user_message(user_input)
                
                if bot_responses:
                    st.write("✅ Response ready!")
                    status.update(label="✅ Complete!", state="complete", expanded=False)
                else:
                    st.write("⚠️ No response generated")
                    status.update(label="⚠️ Issue detected", state="error", expanded=False)
        
        # Display bot responses
        if bot_responses:
            for response in bot_responses:
                # Validate response is not empty
                if response and response.strip():
                    st.session_state.messages.append({"role": "assistant", "content": response})
        else:
            # Fallback if no responses
            fallback = "I'm processing your request. Could you please provide more details?"
            st.session_state.messages.append({"role": "assistant", "content": fallback})
        
        # Rerun to update UI
        st.rerun()


# =============================================================================
# MAIN APP
# =============================================================================

def main():
    """Main application entry point"""
    # Initialize session state
    initialize_session_state()
    
    # Render UI
    render_sidebar()
    render_chat()
    
    # Footer
    st.divider()
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.caption("🔒 Secure | 🚀 Fast | 🎯 Intelligent")


if __name__ == "__main__":
    main()
