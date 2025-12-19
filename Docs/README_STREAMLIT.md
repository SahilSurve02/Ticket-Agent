# 🎫 IT Support Chatbot - Streamlit UI

A professional, user-friendly web interface for the Ticket-Agent chatbot system built with Streamlit.

## 🚀 Features

### Chat Interface
- **Real-time Conversation**: Interactive chat with the AI support agent
- **Multi-Agent System**: Seamlessly switches between ChatbotAgent (troubleshooting) and TicketAgent (ticket creation)
- **Knowledge Base Integration**: Automatically searches KB for solutions

### Sidebar Dashboard
- **User Profile**: Displays logged-in user information (name, email, department, ID)
- **Session Statistics**: 
  - Tickets created count
  - Messages exchanged
  - Session duration
- **Ticket Status Tracker**: Shows current ticket progress (fields completed)
- **Knowledge Base Status**: Real-time KB connection status
- **Device List**: Quick reference to registered devices

### Smart UI Elements
- **Clean Design**: Modern, professional interface with custom styling
- **Responsive Layout**: Works well on different screen sizes
- **Real-time Updates**: Session state management for seamless experience
- **Visual Feedback**: Color-coded status indicators and progress tracking

## 📦 Installation

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```
   
   Or specifically for Streamlit:
   ```bash
   pip install streamlit
   ```

2. **Set up Environment Variables**:
   Make sure you have a `.env` file with:
   ```
   OPENAI_API_KEY=your_api_key_here
   ```

## 🎯 How to Run

### Option 1: Using the Virtual Environment (Recommended)
```bash
D:/Ticket-Agent/.venv/Scripts/python.exe -m streamlit run app.py
```

### Option 2: If Streamlit is in PATH
```bash
streamlit run app.py
```

### Option 3: Using Python directly
```bash
python -m streamlit run app.py
```

The app will automatically open in your browser at: **http://localhost:8501**

## 💡 How to Use

### Starting a Conversation
1. Type your IT issue in the chat input at the bottom
2. The ChatbotAgent will search the knowledge base for solutions
3. If a solution is found, it will provide troubleshooting steps
4. If no solution exists, it will offer to create a support ticket

### Creating a Ticket
1. When the bot asks if you'd like to create a ticket, respond "yes"
2. The TicketAgent takes over and asks structured questions:
   - **Issue Category** (Network, Hardware, Software, Email, Account, General)
   - **Device ID** (from your registered devices)
   - **Priority** (Low, Medium, High, Critical)
   - **Description** (detailed explanation)
   - **Category-specific fields** (varies by issue type)

3. After all fields are collected, you'll see a preview
4. Confirm, edit, or cancel the ticket

### Session Management
- **New Session Button**: Resets the conversation and starts fresh
- **Session Stats**: Track your activity during the current session
- **Ticket Progress**: Monitor how many fields are completed

## 🎨 UI Components Explained

### Main Chat Area
- **Welcome Message**: Shows when you first open the app
- **Chat History**: All previous messages in the session
- **User Messages**: Your inputs (right-aligned)
- **Bot Messages**: AI responses (left-aligned)
- **Chat Input**: Type and send messages at the bottom

### Sidebar (Left Panel)

#### 👤 User Profile
Displays your account information. In production, this would come from authentication.

#### 📊 Session Stats
- **Tickets Created**: Number of tickets submitted in this session
- **Messages**: Total messages exchanged
- **Session Time**: Duration since you started

#### 🎟️ Ticket Status
Shows the current state:
- **No active ticket**: Not in ticket creation mode
- **In Progress (X/Y fields)**: Currently creating a ticket with progress
- **Completed**: All fields filled, ready for preview

#### 📚 Knowledge Base
Indicates if the system can search the KB for solutions.

#### 💻 Your Devices
Expandable list of your registered devices for quick reference when asked.

## 🏗️ Architecture Integration

The Streamlit UI integrates seamlessly with the existing LangGraph workflow:

```
User Input → Streamlit Chat → LangGraph Workflow
                                  ↓
                    ┌─────────────┴─────────────┐
                    ↓                           ↓
              ChatbotAgent                TicketAgent
            (KB Search/Troubleshoot)    (Ticket Collection)
                    ↓                           ↓
              Response → Streamlit → User
```

### Key Components Used
- **LangGraph StateGraph**: The same workflow from `main.py`
- **MemorySaver**: Maintains conversation state across messages
- **AgentState**: Shared state between all components
- **Nodes**: chatbot_node, ticket_collection_node, ticket_preview_node, etc.

## 🎯 Key Features That Make It Meaningful

### 1. **Real User Information**
- Not just placeholders - displays actual user data from session state
- Would integrate with your auth system in production

### 2. **Live Ticket Progress**
- Real-time tracking of ticket field completion
- Shows exactly how many fields are filled vs. required
- Changes based on the selected category (different categories need different fields)

### 3. **Session Statistics**
- Actual message counts from the conversation
- Real session duration timer
- Accurate ticket submission counter

### 4. **Knowledge Base Status**
- Checks if ChromaDB is actually connected
- Shows real connection errors if they occur
- Not just a static indicator

### 5. **Smart Routing**
- Uses the actual LangGraph conditional routing logic
- Seamlessly hands off between agents based on conversation state
- Handles all the edge cases (confirmations, edits, cancels)

### 6. **Device Integration**
- Shows your actual registered devices from state
- Used during ticket creation when asking for device ID
- Real data, not mock data

## 🔧 Customization

### Changing User Info
Edit in `app.py` line ~145:
```python
st.session_state.user_info = {
    "user_id": "YOUR-ID",
    "user_name": "Your Name",
    # ... etc
}
```

### Adding/Removing Devices
Edit in `app.py` line ~153:
```python
st.session_state.user_devices = [
    "Your Device 1",
    "Your Device 2",
]
```

### Styling
Modify the CSS in `app.py` starting at line ~30

## 🆚 Comparison: CLI vs Streamlit

| Feature | CLI (`main.py`) | Streamlit (`app.py`) |
|---------|----------------|---------------------|
| Interface | Terminal | Web Browser |
| History | Linear text | Visual chat bubbles |
| Status Tracking | Manual | Automated dashboard |
| User Info | Printed once | Always visible sidebar |
| Ticket Progress | Text updates | Visual progress tracker |
| Session Management | Restart script | One-click reset button |
| Multi-user | No | Ready (add auth) |
| Mobile Friendly | No | Yes |

## 🚧 Future Enhancements

- **Authentication**: Add login system
- **Multi-user Support**: Session per user with database
- **Ticket History**: View previously submitted tickets
- **Export Chat**: Download conversation logs
- **Dark Mode**: Toggle between themes
- **Admin Panel**: View all tickets and manage KB

## 📝 Notes

- The UI uses the **exact same workflow** as the CLI version
- All agent logic remains unchanged
- State management is handled through Streamlit's session_state
- The memory checkpointer keeps conversation context

## 🐛 Troubleshooting

### App won't start
- Check if Streamlit is installed: `pip list | grep streamlit`
- Verify .env file exists with OPENAI_API_KEY
- Make sure you're in the correct directory

### Knowledge Base not loading
- Check if `chroma_db` directory exists
- Verify `data/kb.json` is present
- Look for error messages in terminal

### Tickets not submitting
- Check `data/tickets.json` exists and is writable
- Verify all required fields are filled
- Look at terminal output for error traces

## 📄 License

Same as the main Ticket-Agent project.

---

**Enjoy your modern IT Support chatbot UI! 🎉**
