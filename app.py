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
# ROUTING CONFIGURATION
# =============================================================================
USE_LLM_ROUTING = os.getenv("USE_LLM_ROUTING", "false").lower() == "true"

# Import LLM router if enabled
if USE_LLM_ROUTING:
    try:
        from src.router import route_chatbot_llm, route_ticket_collection_llm, route_confirmation_llm
        print("[UI ROUTING] Using LLM-based intelligent routing")
    except ImportError as e:
        print(f"[UI ROUTING] LLM router not available, falling back to rule-based: {e}")
        USE_LLM_ROUTING = False

# =============================================================================
# PAGE CONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="OF IT Support Chatbot",
    page_icon="🎫",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS - Gemini AI Inspired Design
st.markdown("""
<style>
    /* === GEMINI-INSPIRED CLEAN DARK THEME === */
    
    /* Main app background */
    .stApp {
        background-color: #1e1e1e;
    }
    
    /* Main content area */
    .main .block-container {
        padding: 2rem 3rem;
        max-width: 1200px;
    }
    
    /* === SIDEBAR STYLING === */
    section[data-testid="stSidebar"] {
        background-color: #171717;
        border-right: 1px solid #2d2d2d;
    }
    
    section[data-testid="stSidebar"] > div {
        padding: 1.5rem 1rem;
    }
    
    /* Sidebar headings */
    section[data-testid="stSidebar"] h3 {
        font-size: 0.875rem;
        font-weight: 600;
        color: #9ca3af;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 1rem;
        padding-left: 0.5rem;
    }
    
    /* Sidebar dividers */
    section[data-testid="stSidebar"] hr {
        margin: 1.5rem 0;
        border: none;
        border-top: 1px solid #2d2d2d;
    }
    
    /* Sidebar metrics */
    section[data-testid="stSidebar"] div[data-testid="stMetricValue"] {
        font-size: 1.5rem;
        font-weight: 600;
        color: #6366f1;
    }
    
    section[data-testid="stSidebar"] div[data-testid="stMetricLabel"] {
        color: #9ca3af;
        font-size: 0.75rem;
    }
    
    /* Sidebar expanders */
    section[data-testid="stSidebar"] .streamlit-expanderHeader {
        background-color: #252525;
        border-radius: 8px;
        padding: 0.75rem;
        font-size: 0.875rem;
        color: #e5e7eb;
        border: 1px solid #2d2d2d;
    }
    
    section[data-testid="stSidebar"] .streamlit-expanderHeader:hover {
        background-color: #2d2d2d;
        border-color: #3d3d3d;
    }
    
    /* === CHAT MESSAGES === */
    .stChatMessage {
        background-color: transparent !important;
        padding: 1.5rem 0;
        border-radius: 0;
        border: none;
        animation: fadeInUp 0.4s ease-out;
    }
    
    @keyframes fadeInUp {
        from {
            opacity: 0;
            transform: translateY(10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
    
    /* User message */
    div[data-testid="stChatMessage"][data-testid="stChatMessageContent"] {
        background-color: transparent;
    }
    
    /* Message content */
    .stChatMessage > div {
        max-width: 800px;
        margin: 0 auto;
    }
    
    /* Message text */
    .stChatMessage p {
        color: #e5e7eb;
        font-size: 0.95rem;
        line-height: 1.6;
        margin: 0;
    }
    
    /* === BUTTONS === */
    .stButton button {
        background-color: #2d2d2d;
        color: #e5e7eb;
        border: 1px solid #3d3d3d;
        border-radius: 20px;
        padding: 0.65rem 1.5rem;
        font-size: 0.875rem;
        font-weight: 500;
        transition: all 0.2s ease;
        height: auto;
    }
    
    .stButton button:hover {
        background-color: #3d3d3d;
        border-color: #4d4d4d;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    
    /* Primary button */
    .stButton button[kind="primary"] {
        background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
        color: white;
        border: none;
        font-weight: 600;
    }
    
    .stButton button[kind="primary"]:hover {
        background: linear-gradient(135deg, #5558e3 0%, #7c3aed 100%);
        box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4);
    }
    
    /* === CHAT INPUT === */
    .stChatInput {
        border-top: 1px solid #2d2d2d;
        padding-top: 1rem;
    }
    
    .stChatInput > div {
        background-color: #2d2d2d;
        border: 1px solid #3d3d3d;
        border-radius: 24px;
        padding: 0.5rem 1rem;
    }
    
    .stChatInput textarea {
        color: #e5e7eb;
        font-size: 0.95rem;
    }
    
    .stChatInput > div:focus-within {
        border-color: #6366f1;
        box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
    }
    
    /* === HEADERS === */
    h1 {
        color: #f9fafb;
        font-size: 1.75rem;
        font-weight: 600;
        margin-bottom: 0.25rem;
    }
    
    h2, h3 {
        color: #e5e7eb;
        font-weight: 600;
    }
    
    /* Caption text */
    .stCaption {
        color: #9ca3af;
        font-size: 0.875rem;
    }
    
    /* === ALERTS & INFO BOXES === */
    .stAlert {
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 12px;
        color: #e5e7eb;
    }
    
    .stSuccess {
        background-color: rgba(34, 197, 94, 0.1);
        border-left: 4px solid #22c55e;
    }
    
    .stWarning {
        background-color: rgba(251, 146, 60, 0.1);
        border-left: 4px solid #fb923c;
    }
    
    .stInfo {
        background-color: rgba(59, 130, 246, 0.1);
        border-left: 4px solid #3b82f6;
    }
    
    /* === CUSTOM CONTAINERS === */
    div[data-testid="column"] {
        padding: 0.25rem;
    }
    
    /* === LOADING SPINNER === */
    .stSpinner > div {
        border-color: #6366f1 !important;
    }
    
    /* === SCROLLBAR === */
    ::-webkit-scrollbar {
        width: 8px;
        height: 8px;
    }
    
    ::-webkit-scrollbar-track {
        background: #171717;
    }
    
    ::-webkit-scrollbar-thumb {
        background: #3d3d3d;
        border-radius: 4px;
    }
    
    ::-webkit-scrollbar-thumb:hover {
        background: #4d4d4d;
    }
    
    /* === SELECTION BUTTONS (Device, Category, Priority) === */
    div[data-testid="column"] .stButton button {
        width: 100%;
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 12px;
        padding: 1rem;
        font-size: 0.9rem;
        font-weight: 500;
        text-align: center;
        min-height: 60px;
        display: flex;
        align-items: center;
        justify-content: center;
        transition: all 0.2s ease;
        position: relative;
        overflow: hidden;
    }
    
    div[data-testid="column"] .stButton button::before {
        content: '';
        position: absolute;
        top: 50%;
        left: 50%;
        width: 0;
        height: 0;
        border-radius: 50%;
        background: rgba(99, 102, 241, 0.1);
        transform: translate(-50%, -50%);
        transition: width 0.3s, height 0.3s;
    }
    
    div[data-testid="column"] .stButton button:hover::before {
        width: 300px;
        height: 300px;
    }
    
    div[data-testid="column"] .stButton button:hover {
        background-color: #2d2d2d;
        border-color: #6366f1;
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(99, 102, 241, 0.3);
    }
    
    /* === MARKDOWN STYLING === */
    .stMarkdown {
        color: #e5e7eb;
    }
    
    /* === JSON/CODE DISPLAY === */
    .stJson, .stCode {
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 8px;
    }
</style>
""", unsafe_allow_html=True)


# =============================================================================
# WORKFLOW GRAPH SETUP (Same as main.py)
# =============================================================================

def route_chatbot_rules(state: AgentState):
    """Routes from chatbot based on state - Rule-based implementation"""
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


def route_ticket_collection_rules(state: AgentState):
    """Routes from ticket collection - Rule-based implementation"""
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


def route_confirmation_rules(state: AgentState):
    """Routes from confirmation based on user's choice - Rule-based implementation"""
    action = state.get("confirmation_action", "")
    
    if action == "submit":
        return "submit_ticket"
    elif action in ["edit", "cancel"]:
        return END
    
    return END


def route_chatbot(state: AgentState):
    """Main chatbot router - uses LLM or rules based on configuration"""
    if USE_LLM_ROUTING:
        result = route_chatbot_llm(state)
        return END if result == "END" else result
    return route_chatbot_rules(state)


def route_ticket_collection(state: AgentState):
    """Main ticket collection router - uses LLM or rules based on configuration"""
    if USE_LLM_ROUTING:
        result = route_ticket_collection_llm(state)
        return END if result == "END" else result
    return route_ticket_collection_rules(state)


def route_confirmation(state: AgentState):
    """Main confirmation router - uses LLM or rules based on configuration"""
    if USE_LLM_ROUTING:
        result = route_confirmation_llm(state)
        return END if result == "END" else result
    return route_confirmation_rules(state)


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
    
    # Check if this is a solution feedback prompt
    if "Did this help solve your issue?" in content:
        # Split content to show solution and then feedback buttons
        parts = content.split("Did this help solve your issue?")
        solution_text = parts[0].strip()
        
        st.markdown(solution_text)
        st.divider()
        
        st.markdown("**Did this help solve your issue?**")
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            if st.button("👍 Yes, Solved!", key=f"{message_key}_thumbs_up", 
                        use_container_width=True, type="primary"):
                return "yes solved"
        with col2:
            if st.button("👎 No, Still Issues", key=f"{message_key}_thumbs_down", 
                        use_container_width=True):
                return "no still issues"
        with col3:
            st.caption("Your feedback helps us improve!")
        return None
    
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
    
    # Check if this is a connection type selection (Network category)
    elif "What type of connection" in content and "WiFi" in content and "Ethernet" in content:
        st.markdown("### Connection Type?")
        st.markdown("")
        
        connection_types = [
            ("📶 WiFi", "Wireless connection", "WiFi"),
            ("🔌 Ethernet/Wired", "Wired network", "Ethernet/Wired"),
            ("🔒 VPN", "Virtual Private Network", "VPN")
        ]
        
        cols = st.columns(3)
        for idx, (label, desc, value) in enumerate(connection_types):
            with cols[idx]:
                if st.button(label, key=f"{message_key}_conn_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is account type selection (Account category)
    elif "What type of account" in content and "Windows/Computer Login" in content:
        st.markdown("### Account Type?")
        st.markdown("")
        
        account_types = [
            ("🖥️ Windows Login", "Computer login", "Windows/Computer Login"),
            ("📧 Email", "Email account", "Email"),
            ("🔒 VPN", "VPN access", "VPN"),
            ("📱 Application", "App account", "Application")
        ]
        
        cols = st.columns(2)
        for idx, (label, desc, value) in enumerate(account_types):
            with cols[idx % 2]:
                if st.button(label, key=f"{message_key}_acct_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is hardware component selection (Hardware category)
    elif "Which hardware component" in content and "Display/Monitor" in content:
        st.markdown("### Hardware Component?")
        st.markdown("")
        
        components = [
            ("🖥️ Display/Monitor", "Screen issues", "Display/Monitor"),
            ("⌨️ Keyboard/Mouse", "Input devices", "Keyboard/Mouse"),
            ("🔋 Battery", "Power issues", "Battery"),
            ("🔊 Audio/Speakers", "Sound problems", "Audio/Speakers"),
            ("⚙️ Other", "Other hardware", "Other")
        ]
        
        cols = st.columns(3)
        for idx, (label, desc, value) in enumerate(components):
            with cols[idx % 3]:
                if st.button(label, key=f"{message_key}_hw_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is email client selection (Email category)
    elif "Which email application" in content and "Outlook Desktop" in content:
        st.markdown("### Email Client?")
        st.markdown("")
        
        email_clients = [
            ("📨 Outlook Desktop", "Desktop app", "Outlook Desktop"),
            ("🌐 Outlook Web", "Web browser", "Outlook Web"),
            ("📱 Mobile App", "Phone/tablet", "Mobile App"),
            ("⚙️ Other", "Other client", "Other")
        ]
        
        cols = st.columns(2)
        for idx, (label, desc, value) in enumerate(email_clients):
            with cols[idx % 2]:
                if st.button(label, key=f"{message_key}_email_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is email action selection (Email category)
    elif "What action is not working" in content and "Sending emails" in content:
        st.markdown("### What's Not Working?")
        st.markdown("")
        
        actions = [
            ("📤 Sending emails", "Can't send", "Sending emails"),
            ("📥 Receiving emails", "Can't receive", "Receiving emails"),
            ("⛔ Both", "Send & receive", "Both"),
            ("📅 Other", "Calendar/contacts", "Other (calendar, contacts, etc.)")
        ]
        
        cols = st.columns(2)
        for idx, (label, desc, value) in enumerate(actions):
            with cols[idx % 2]:
                if st.button(label, key=f"{message_key}_action_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is physical damage question (yes/no)
    elif "visible physical damage" in content.lower() and "(yes/no)" in content.lower():
        st.markdown("### Physical Damage?")
        st.markdown("")
        
        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Yes", key=f"{message_key}_damage_yes", use_container_width=True):
                return "yes"
        with col2:
            if st.button("❌ No", key=f"{message_key}_damage_no", use_container_width=True):
                return "no"
        return None
    
    # Check if this is a device selection prompt
    if "Which device is affected?" in content or "couldn't find that device" in content:
        lines = content.split('\n')
        text_part = lines[0]
        devices = [line.strip().replace('• ', '') for line in lines if line.strip().startswith('•')]
        
        st.markdown(f"### {text_part}")
        st.markdown("")  # Add spacing
        
        # Determine icon for each device
        cols = st.columns(min(len(devices), 3))
        for idx, device in enumerate(devices):
            icon = "🖥️" if any(x in device for x in ["Dell", "HP", "Latitude"]) else \
                   "💻" if "MacBook" in device else \
                   "📱" if any(x in device for x in ["iPad", "iPhone"]) else \
                   "🖨️" if "Printer" in device else "🖥️"
            with cols[idx % 3]:
                if st.button(f"{icon} **{device}**", key=f"{message_key}_device_{idx}", 
                           use_container_width=True):
                    return device
        return None
    
    # Check if this is a category selection prompt
    elif "What category best describes your issue?" in content:
        st.markdown("### What category best describes your issue?")
        st.markdown("")  # Add spacing
        
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
                if st.button(emoji_name, key=f"{message_key}_cat_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is a priority selection prompt
    elif "Priority level?" in content or "Please choose a valid priority level" in content:
        st.markdown("### Priority level?")
        st.markdown("")
        
        priorities = [
            ("🟢 Low", "Can wait • Non-urgent", "Low"),
            ("🟡 Medium", "Affecting work • Important", "Medium"),
            ("🟠 High", "Blocking work • Urgent", "High"),
            ("🔴 Critical", "System down • Emergency", "Critical")
        ]
        
        cols = st.columns(2)
        for idx, (emoji_name, desc, value) in enumerate(priorities):
            with cols[idx % 2]:
                if st.button(emoji_name, key=f"{message_key}_pri_{idx}", 
                           help=desc, use_container_width=True):
                    return value
        return None
    
    # Check if this is a ticket preview with options
    elif "📋 **Ticket Preview**" in content or "Ticket Preview" in content:
        # Extract ticket preview content
        parts = content.split('**Options:**')
        preview_content = parts[0]
        
        # Modern card-style ticket preview
        st.markdown("### 📋 Ticket Preview")
        
        # User info card with 2x2 grid
        with st.container():
            st.markdown("#### 👤 User Information")
            
            # Extract user info
            lines = preview_content.split('\n')
            user_info = {}
            in_user_section = False
            
            for line in lines:
                if '### 👤 User Information' in line:
                    in_user_section = True
                elif '### 🎫 Issue Details' in line:
                    in_user_section = False
                elif in_user_section and '**' in line and ':' in line:
                    key_val = line.split(':', 1)
                    key = key_val[0].replace('**', '').strip()
                    val = key_val[1].strip() if len(key_val) > 1 else ''
                    user_info[key] = val
            
            # Display in 2x2 grid
            col1, col2 = st.columns(2)
            user_items = list(user_info.items())
            
            with col1:
                if len(user_items) > 0:
                    st.markdown(f"**{user_items[0][0]}:** {user_items[0][1]}")
                if len(user_items) > 2:
                    st.markdown(f"**{user_items[2][0]}:** {user_items[2][1]}")
                if len(user_items) > 4:
                    st.markdown(f"**{user_items[4][0]}:** {user_items[4][1]}")
            
            with col2:
                if len(user_items) > 1:
                    st.markdown(f"**{user_items[1][0]}:** {user_items[1][1]}")
                if len(user_items) > 3:
                    st.markdown(f"**{user_items[3][0]}:** {user_items[3][1]}")
        
        st.divider()
        
        # Issue details
        with st.container():
            st.markdown("#### 🎫 Issue Details")
            issue_info = {}
            in_issue_section = False
            
            for line in lines:
                if '### 🎫 Issue Details' in line:
                    in_issue_section = True
                elif '**Description (AI-Generated):**' in line:
                    in_issue_section = False
                elif in_issue_section and '**' in line and ':' in line:
                    key_val = line.split(':', 1)
                    key = key_val[0].replace('**', '').strip()
                    val = key_val[1].strip() if len(key_val) > 1 else ''
                    if key:
                        issue_info[key] = val
            
            for key, val in issue_info.items():
                if key == 'Priority':
                    color = {'Low': '🟢', 'Medium': '🟡', 'High': '🟠', 'Critical': '🔴'}.get(val.strip(), '⚪')
                    st.markdown(f"**{key}:** {color} {val}")
                else:
                    st.markdown(f"**{key}:** {val}")
        
        # Description (if exists)
        if 'Description (AI-Generated)' in preview_content or '**Description:**' in preview_content:
            st.divider()
            st.markdown("#### 📝 Description")
            # Try both variations
            desc_start = preview_content.find('**Description (AI-Generated):**')
            if desc_start == -1:
                desc_start = preview_content.find('**Description:**')
            if desc_start != -1:
                # Extract description text properly
                desc_text = preview_content[desc_start:]
                desc_text = desc_text.replace('**Description (AI-Generated):**', '').replace('**Description:**', '').strip()
                # Remove any trailing options text
                if '**Options:**' in desc_text:
                    desc_text = desc_text.split('**Options:**')[0].strip()
                # Display the description
                if desc_text and desc_text != 'None':
                    st.markdown(desc_text)
        
        st.divider()
        st.markdown("### What would you like to do?")
        
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
        # === MODERN HEADER ===
        st.markdown("""
<div style="
    text-align: center;
    padding: 1rem 0 1.5rem 0;
    border-bottom: 1px solid #3d3d3d;
    margin-bottom: 1.5rem;
">
    <div style="font-size: 1.75rem; margin-bottom: 0.25rem;">🎫</div>
    <div style="font-size: 1.1rem; font-weight: 700; color: #f9fafb;">IT Support</div>
    <div style="font-size: 0.75rem; color: #6366f1; margin-top: 0.25rem;">Multi-Agent AI</div>
</div>
        """, unsafe_allow_html=True)
        
        # === USER PROFILE CARD ===
        user = st.session_state.user_info
        st.markdown("""
<div style="
    background: linear-gradient(135deg, #2d2d2d 0%, #252525 100%);
    border: 1px solid #3d3d3d;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 4px 12px rgba(0,0,0,0.2);
">
    <div style="display: flex; align-items: center; margin-bottom: 0.75rem;">
        <div style="
            width: 40px;
            height: 40px;
            border-radius: 50%;
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            margin-right: 0.75rem;
        ">👤</div>
        <div>
            <div style="font-size: 0.95rem; font-weight: 600; color: #f9fafb;">{}</div>
            <div style="font-size: 0.7rem; color: #9ca3af;">{}</div>
        </div>
    </div>
    <div style="
        padding: 0.75rem;
        background-color: #1e1e1e;
        border-radius: 8px;
        font-size: 0.75rem;
        line-height: 1.8;
        color: #9ca3af;
    ">
        <div style="margin-bottom: 0.3rem;">📧 {}</div>
        <div style="margin-bottom: 0.3rem;">📞 {}</div>
        <div>🆔 {}</div>
    </div>
</div>
        """.format(
            user['user_name'],
            user['department'],
            user['email'],
            user['phone'],
            user['user_id']
        ), unsafe_allow_html=True)
        
        # === SESSION METRICS GRID ===
        duration = datetime.now() - st.session_state.session_start
        minutes = int(duration.total_seconds() / 60)
        status = get_ticket_status()
        status_label = "Active" if "In Progress" in status else "Idle"
        status_color = "#fb923c" if "Active" in status_label else "#6366f1"
        
        st.markdown("""
<div style="
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
">
    <div style="
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 10px;
        padding: 0.75rem;
        text-align: center;
    ">
        <div style="font-size: 1.5rem; font-weight: 700; color: #6366f1;">{}</div>
        <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">TICKETS</div>
    </div>
    <div style="
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 10px;
        padding: 0.75rem;
        text-align: center;
    ">
        <div style="font-size: 1.5rem; font-weight: 700; color: #8b5cf6;">{}</div>
        <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">MESSAGES</div>
    </div>
    <div style="
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 10px;
        padding: 0.75rem;
        text-align: center;
    ">
        <div style="font-size: 1.5rem; font-weight: 700; color: #22c55e;">{} min</div>
        <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">TIME</div>
    </div>
    <div style="
        background-color: #252525;
        border: 1px solid #3d3d3d;
        border-radius: 10px;
        padding: 0.75rem;
        text-align: center;
    ">
        <div style="font-size: 1.5rem; font-weight: 700; color: {};">{}</div>
        <div style="font-size: 0.7rem; color: #9ca3af; margin-top: 0.25rem;">STATUS</div>
    </div>
</div>
        """.format(
            st.session_state.tickets_submitted,
            len(st.session_state.messages),
            minutes,
            status_color,
            status_label
        ), unsafe_allow_html=True)
        
        # === KNOWLEDGE BASE STATUS ===
        kb_connected = "✓" in st.session_state.kb_status
        kb_icon = "✓" if kb_connected else "⚠"
        kb_text = "Connected" if kb_connected else "Unavailable"
        kb_bg = "rgba(34, 197, 94, 0.15)" if kb_connected else "rgba(251, 146, 60, 0.15)"
        kb_border = "#22c55e" if kb_connected else "#fb923c"
        
        st.markdown("""
<div style="
    background: {};
    border: 1px solid {};
    border-radius: 10px;
    padding: 0.75rem;
    margin-bottom: 1.5rem;
    text-align: center;
">
    <div style="font-size: 0.7rem; color: #9ca3af; margin-bottom: 0.25rem;">KNOWLEDGE BASE</div>
    <div style="font-size: 0.9rem; font-weight: 600; color: #f9fafb;">{} {}</div>
</div>
        """.format(kb_bg, kb_border, kb_icon, kb_text), unsafe_allow_html=True)
        
        # === DEVICES SECTION ===
        st.markdown("""
<div style="
    font-size: 0.7rem;
    font-weight: 600;
    color: #9ca3af;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.75rem;
    padding-left: 0.25rem;
">💻 Your Devices</div>
        """, unsafe_allow_html=True)
        
        with st.expander("🔽 View All Devices", expanded=False):
            for idx, device in enumerate(st.session_state.user_devices):
                icon = "🖥️" if any(x in device for x in ["Dell", "HP", "MacBook"]) else ("📱" if any(x in device for x in ["iPad", "iPhone"]) else "🖨️")
                st.markdown(f"""
<div style="
    background-color: #252525;
    border: 1px solid #3d3d3d;
    border-radius: 6px;
    padding: 0.5rem 0.75rem;
    margin-bottom: 0.5rem;
    font-size: 0.8rem;
    color: #e5e7eb;
">
    {icon} {device}
</div>
                """, unsafe_allow_html=True)
        
        # === ACTIONS ===
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🔄 New Session", use_container_width=True, type="primary"):
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.rerun()
        
        # === DEVELOPER DEBUG ===
        with st.expander("🛠️ Debug", expanded=False):
            st.json(st.session_state.agent_state)


def render_chat():
    """Render the main chat interface"""
    # Glowing title with special OF emphasis
    st.markdown("""
<div style="text-align: center; margin-bottom: 1rem;">
    <h1 style="
        margin: 0;
        padding: 0;
        font-size: 2rem;
        font-weight: 700;
        letter-spacing: 0.02em;
    ">
        <span style="
            display: inline-block;
            background: linear-gradient(135deg, #f59e0b 0%, #f97316 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            filter: drop-shadow(0 0 20px rgba(249, 115, 22, 0.6)) drop-shadow(0 0 40px rgba(245, 158, 11, 0.4));
            animation: glow 2s ease-in-out infinite alternate;
            font-weight: 800;
        ">OF</span>
        <span style="
            color: #e5e7eb;
            margin-left: 0.5rem;
        ">IT Support Chatbot</span>
    </h1>
</div>
<style>
    @keyframes glow {
        from {
            filter: drop-shadow(0 0 15px rgba(249, 115, 22, 0.5)) drop-shadow(0 0 30px rgba(245, 158, 11, 0.3));
        }
        to {
            filter: drop-shadow(0 0 25px rgba(249, 115, 22, 0.8)) drop-shadow(0 0 50px rgba(245, 158, 11, 0.6));
        }
    }
</style>
    """, unsafe_allow_html=True)
    st.caption("Powered by Multi-Agent AI System | LangGraph + GPT-4")
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Welcome message if no messages
    if not st.session_state.messages:
        st.markdown("""
<div style="
    background-color: #252525;
    padding: 2rem;
    border-radius: 16px;
    border: 1px solid #3d3d3d;
    margin: 2rem 0;
    text-align: center;
">
    <h2 style="margin-top: 0; color: #f9fafb; font-size: 1.5rem;">👋 Welcome!</h2>
    <p style="line-height: 1.8; color: #9ca3af; margin-bottom: 1.5rem; font-size: 0.95rem;">
        I'm your AI-powered IT assistant, ready to help with your technical issues.
    </p>
    <div style="display: flex; justify-content: center; gap: 2rem; flex-wrap: wrap; margin-top: 1.5rem;">
        <div style="flex: 1; min-width: 150px; max-width: 200px;">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🔍</div>
            <div style="color: #e5e7eb; font-size: 0.85rem;">Search KB</div>
        </div>
        <div style="flex: 1; min-width: 150px; max-width: 200px;">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🛠️</div>
            <div style="color: #e5e7eb; font-size: 0.85rem;">Troubleshoot</div>
        </div>
        <div style="flex: 1; min-width: 150px; max-width: 200px;">
            <div style="font-size: 1.5rem; margin-bottom: 0.5rem;">🎫</div>
            <div style="color: #e5e7eb; font-size: 0.85rem;">Create Tickets</div>
        </div>
    </div>
    <p style="margin-top: 1.5rem; margin-bottom: 0; color: #6366f1; font-weight: 500; font-size: 0.9rem;">
        Describe your problem to get started
    </p>
</div>
        """, unsafe_allow_html=True)
    
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
