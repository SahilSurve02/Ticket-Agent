# Ticket Agent - Complete Repository Documentation

## 📋 Project Overview

**Ticket Agent** is an intelligent IT support chatbot system built with LangGraph and LangChain that provides first-line IT support and automated ticket creation. The system combines a conversational AI interface with a knowledge base (KB) to troubleshoot issues and seamlessly transition users to ticket creation when self-service solutions don't work.

### Key Features:
- **Multi-phase conversation flow**: Chatbot → Ticket Collection → Ticket Preview → Confirmation
- **Knowledge Base Integration**: Vector database (ChromaDB) with semantic search for solutions
- **Stateful conversation management**: Uses LangGraph for maintaining conversation state across turns
- **Ticket creation workflow**: Step-by-step form filling with validation
- **GPT-4o-mini LLM**: Fast, cost-effective language model for troubleshooting

---

## 📁 Repository Structure

```
Ticket-Agent/
├── main.py                 # Entry point, LangGraph workflow orchestration
├── requirements.txt        # Python dependencies
├── test_flow.md           # Test cases and expected flows
├── src/
│   ├── kb.py              # Knowledge base management (ChromaDB integration)
│   ├── nodes.py           # LangGraph node implementations
│   ├── state.py           # State schema definitions
│   └── __pycache__/
├── data/
│   └── kb.json            # Knowledge base documents (IT support solutions)
└── chroma_db/             # Vector database persistence directory
    ├── chroma.sqlite3     # Vector database file
    └── [collection-id]/   # ChromaDB collection storage
```

---

## 🔧 Technology Stack

### Core Libraries:
- **LangGraph**: State machine for multi-step workflows
- **LangChain**: LLM orchestration and prompt management
- **OpenAI**: GPT-4o-mini model for conversational AI
- **ChromaDB**: Vector database for semantic search
- **Pydantic**: Data validation and schema definitions

### Supporting Libraries:
- **FastAPI**: Web API framework (not currently used)
- **Uvicorn**: ASGI server
- **python-dotenv**: Environment variable management
- **Loguru**: Logging framework

---

## 📝 Detailed File Explanations

### 1. **src/state.py** - State Schema Definitions

This file defines the data structures that flow through the LangGraph workflow.

#### `TicketSchema` (Pydantic Model)
Represents a support ticket with the following fields:
- `issue_summary`: Brief description of the problem (auto-extracted from conversation)
- `device_id`: The specific device (Dell Latitude 5420, iPad Pro, etc.)
- `priority`: Severity level (Low, Medium, High, Critical)
- `description`: Optional detailed description provided by user

```python
class TicketSchema(BaseModel):
    issue_summary: Optional[str] = None
    device_id: Optional[str] = None
    priority: Optional[str] = None
    description: Optional[str] = None
```

#### `AgentState` (TypedDict)
Central state object that flows through the entire LangGraph workflow:

| Field | Type | Purpose |
|-------|------|---------|
| `messages` | List of LangChain messages | Maintains full conversation history |
| `ticket` | TicketSchema | Current ticket being created |
| `user_devices` | List[str] | Available devices for the user |
| `kb_used` | bool | Whether KB was consulted |
| `kb_confidence` | str | Confidence of KB results (high/medium/low) |
| `detected_category` | str | Auto-detected issue category |
| `ticket_preview_shown` | bool | Whether preview was displayed |
| `awaiting_confirmation` | bool | Waiting for user confirmation |
| `last_question` | str | Tracks what question was asked (device/priority/description) |

---

### 2. **src/kb.py** - Knowledge Base Management

This module manages the vector database containing IT support solutions using ChromaDB.

#### `KnowledgeBase` Class
Initializes ChromaDB with OpenAI embeddings for semantic search.

```python
class KnowledgeBase:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        self.vectorstore = Chroma(...)  # Persistent vector store
```

**Key Methods:**

| Method | Purpose |
|--------|---------|
| `load_knowledge_base()` | Loads documents from `data/kb.json` into vector store |
| `search_knowledge()` | Semantic search with similarity scoring |
| `get_best_solution()` | Multi-strategy KB search with fallback logic |
| `detect_category()` | Identifies issue category from user message |
| `initialize_kb_with_check()` | Validates and initializes KB with error handling |

#### `KBDocument` Schema
Structure of each knowledge base document:

```python
class KBDocument(BaseModel):
    title: str                    # Article title
    category: str                 # WiFi, Login, Hardware, Software
    issue_type: str              # Specific issue type
    symptoms: List[str]          # Common symptoms users report
    solution: str                # Step-by-step solution
    severity: str                # Low, Medium, High, Critical
    related_errors: List[str]    # Error messages
    prerequisites: List[str]     # Requirements
    success_rate: Optional[float]# Historical success rate
    estimated_time: Optional[str]# Time to resolve
```

#### Search Strategy
Uses 4-tier fallback approach:
1. **Direct semantic search** (threshold: 0.85)
2. **Context-enhanced search** using conversation history
3. **Broadened search** without category filter
4. **Generic response** if no match found

---

### 3. **src/nodes.py** - LangGraph Node Implementations

Defines the processing logic for each node in the workflow graph. Each node is an async function that processes state and returns state updates.

#### **Node 1: `chatbot_node`** - First-Line Support
**Purpose**: Provide troubleshooting advice from KB

**Flow**:
1. Extract user's issue from latest message
2. Detect category (WiFi, Login, Hardware, Software)
3. Search knowledge base for matching solutions
4. Return solutions if found, otherwise provide generic advice
5. Ask user if they want to create a ticket when solution doesn't work

**Key Logic**:
- Bypasses LLM if user is already in ticket collection phase (`last_question` is set)
- Formats KB solutions in system prompt for LLM
- Triggers handoff to ticket creation with "handoff_to_ticket" marker

#### **Node 2: `ticket_collection_node`** - Form Filling Phase 1
**Purpose**: Collect ticket information step-by-step

**Collection Sequence**:
1. **Extract issue summary** (auto-extracted from conversation once)
2. **Ask for device** (required - matches user input to available devices)
3. **Ask for priority** (required - Low/Medium/High/Critical)
4. **Ask for description** (optional - user can skip)

**Smart Extraction Logic**:
- Uses LLM with TicketSchema tool binding for field extraction
- Only extracts relevant field when `last_question` matches
- Prevents auto-filling of description from conversation
- Uses context-aware prompts for matching devices

**Returns**: Updated ticket state + next question to ask (if any field missing)

#### **Node 3: `ticket_preview_node`** - Phase 2
**Purpose**: Display ticket preview for confirmation

**Display Format**:
```
📋 **Ticket Preview**

**Issue Summary:** [Extracted summary]
**Device:** [Selected device]
**Priority:** [Selected priority]
**Description:** [Optional description]

Options: submit, edit, cancel
```

**Output**: Sets `awaiting_confirmation` flag

#### **Node 4: `ticket_confirmation_node`** - Phase 3
**Purpose**: Handle user's confirmation action

**Action Routing**:
- `submit/yes/confirm` → Submit ticket
- `edit/change` → Return to ticket collection
- `cancel/no/back` → Reset ticket and return to chatbot
- Other responses → Request clarification

**Resets ticket properly** on cancellation.

---

### 4. **main.py** - Workflow Orchestration

The heart of the application that combines all components into a functioning LangGraph workflow.

#### Routing Functions

##### `route_chatbot(state)` - From Chatbot Node
Determines next node after chatbot processing:
- `awaiting_confirmation` → ticket_confirmation (user is reviewing preview)
- Incomplete ticket fields → ticket_collection (resume filling)
- "handoff_to_ticket" in message → ticket_collection (user wants ticket)
- Otherwise → END (wait for user response)

##### `route_ticket_collection(state)` - From Collection Node
Checks if all required fields are complete:
- All fields filled (`issue_summary`, `device_id`, `priority`) → ticket_preview
- Otherwise → END (wait for user response)

##### `route_confirmation(state)` - From Confirmation Node
Routes based on user's action:
- `submit` → submit_ticket node
- `edit` → back to ticket_collection
- `cancel` → back to chatbot
- Invalid → stay in ticket_confirmation

#### Graph Structure
```
Entry: chatbot
    ↓
[chatbot_node] --route_chatbot--> ticket_collection | ticket_confirmation | END
    ↑                                    ↓
    |                          [ticket_collection_node]
    |                                    ↓
    |                          route_ticket_collection
    |                                    ↓
    |                            ticket_preview
    |                                    ↓
    |                          [ticket_preview_node]
    |                                    ↓
    |                          ticket_confirmation
    |                                    ↓
    |                          [ticket_confirmation_node]
    |                                    ↓
    |                          route_confirmation
    |                                    ↓
    └-------- submit_ticket | ticket_collection | chatbot
```

#### State Initialization
```python
initial_input = {
    "user_devices": ["Dell Latitude 5420", "iPad Pro"],
    "ticket": {...},
    "ticket_preview_shown": False,
    "awaiting_confirmation": False,
    "last_question": None
}
```

#### Execution Model
- Uses `MemorySaver` checkpointer for state persistence
- Maintains `thread_id` for multi-turn conversations
- Streams responses as nodes complete
- Shows node name and AI messages to user

---

### 5. **data/kb.json** - Knowledge Base Content

Contains 4 sample IT support solutions in JSON format:

#### Documents Included:

1. **WiFi Connection Drops Intermittently**
   - Category: WiFi
   - Severity: Medium
   - Success Rate: 85%
   - Solutions: Driver updates, channel changes, power settings, network reset

2. **Unable to Connect to Corporate WiFi**
   - Category: WiFi
   - Severity: High
   - Success Rate: 90%
   - Solutions: Credential verification, network reconnection, domain check

3. **Login Failed - Account Locked**
   - Category: Login
   - Severity: High
   - Success Rate: 95%
   - Solutions: Wait for unlock, password reset, MFA enablement

4. **Slow Computer Performance**
   - Category: Hardware
   - Severity: Medium
   - Success Rate: 75%
   - Solutions: Task Manager analysis, disk cleanup, malware scan, RAM upgrade

---

### 6. **requirements.txt** - Dependencies

| Package | Purpose |
|---------|---------|
| langgraph | State machine workflow engine |
| langchain, langchain-core | LLM integration framework |
| langchain-openai | OpenAI API wrapper |
| langchain-community | Community integrations |
| pydantic | Data validation |
| chromadb | Vector database |
| tiktoken | Token counting for OpenAI |
| fastapi, uvicorn | Web framework (prepared) |
| python-dotenv | Environment variable loading |
| loguru | Logging framework |
| pytest, pytest-asyncio | Testing |
| aiofiles | Async file operations |

---

### 7. **test_flow.md** - Testing Documentation

Comprehensive test cases documenting:

#### Test Case 1: Complete Ticket Flow
Step-by-step expected interactions from initial issue report to ticket submission.

**Key Assertions**:
- ✅ Device must be explicitly asked (never auto-selected)
- ✅ Priority must be explicitly asked
- ✅ Description must NOT be auto-filled from conversation
- ✅ Preview must be shown before submission
- ✅ Confirmation required before submission

#### Test Case 2: Cancel Flow
Verifies ticket cancellation properly resets state.

#### Test Case 3: Edit Flow
Verifies user can return to modify ticket fields.

---

## 🔄 Complete User Flow Example

```
User: "Hi, my laptop is very slow"
    ↓
[chatbot_node]: Searches KB for "slow" → Finds "Slow Computer Performance"
    → Provides solution steps

User: "still not working"
    ↓
[chatbot_node]: Recognizes persistent issue → Asks about creating ticket

User: "yes"
    ↓
route_chatbot detects "handoff_to_ticket"
    → Routes to ticket_collection

[ticket_collection_node]: 
    - Auto-extracts issue_summary: "Laptop is very slow"
    - Asks: "Which device?" (device_id is None)

User: "Dell"
    ↓
[ticket_collection_node]:
    - Extracts device_id: "Dell Latitude 5420"
    - Asks: "What priority?" (priority is None)

User: "High"
    ↓
[ticket_collection_node]:
    - Extracts priority: "High"
    - Asks: "Additional details?" (description is None)

User: "no"
    ↓
[ticket_collection_node]:
    - Sets description: "None provided"
    - All fields complete!
    
route_ticket_collection:
    → Routes to ticket_preview

[ticket_preview_node]:
    - Shows formatted preview
    - Sets awaiting_confirmation = true

User: "submit"
    ↓
[ticket_confirmation_node]:
    - Detects "submit" action
    - Sets confirmation_action = "submit"

route_confirmation:
    → Routes to submit_ticket

[submit_ticket]:
    - Creates ticket with UUID
    - Returns to chatbot

User continues conversation or creates another ticket...
```

---

## 🚀 How to Run

### 1. Setup Environment
```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file
OPENAI_API_KEY=your_api_key_here
```

### 2. Initialize Knowledge Base
The KB is automatically initialized on first run from `data/kb.json`.

### 3. Start Chat
```bash
python main.py
```

### 4. Interact
- Type your IT support issue
- Follow the chatbot's troubleshooting steps
- Create ticket if needed
- Type 'q' or 'quit' to exit

---

## 🔑 Key Design Patterns

### 1. **State-Based Routing**
Uses conditional edges to route based on state fields:
- `last_question`: Prevents re-asking questions
- `awaiting_confirmation`: Routes to confirmation phase
- `ticket` fields: Checks completion status

### 2. **LLM Tool Binding**
TicketSchema is bound as a tool to LLM for structured extraction:
```python
llm_with_tools = llm.bind_tools([TicketSchema])
```
Forces LLM to return structured data instead of free text.

### 3. **Message-Based Handoffs**
Uses marker strings in messages for routing:
- `"handoff_to_ticket"` signals transition to ticket collection
- Detectable in routing functions

### 4. **Semantic Search**
ChromaDB with OpenAI embeddings for intelligent KB search:
- Converts natural language to embeddings
- Finds similar solutions based on meaning
- Returns confidence scores

### 5. **Multi-Turn State Persistence**
Uses LangGraph's checkpointer to maintain state:
- `thread_id` per conversation
- State survives between turns
- No need to reparse history

---

## 🐛 Known Implementation Details

### Prevent Auto-Population Issues
- Ticket description is NOT auto-extracted from conversation
- Only `issue_summary` is auto-extracted (on first request)
- Device and priority always require explicit user input
- Uses `last_question` flag to track what was asked

### Error Handling
- KB initialization gracefully falls back if file missing
- KB search failures don't crash the chatbot
- Invalid responses prompt for clarification
- Device matching is fuzzy (accepts "Dell" for "Dell Latitude 5420")

### Performance Optimizations
- KB is initialized once at startup (global variable)
- Vector embeddings are cached by ChromaDB
- Uses embedding-3-small for cost efficiency
- Messages use LangGraph's `add_messages` reducer

---

## 🎯 Extensions & Future Work

Potential enhancements:
1. **Database Integration**: Store tickets in SQL database
2. **Email Notifications**: Send ticket confirmations
3. **Web Interface**: Replace CLI with web UI
4. **Priority-Based Routing**: Route critical tickets to human agents
5. **Analytics**: Track solution effectiveness and common issues
6. **Multi-Language**: Support for multiple languages
7. **Agent Assignment**: Route to specific tech support agents
8. **Ticket Updates**: Allow ticket modifications after creation
9. **Escalation Rules**: Automatic escalation for persistent issues
10. **KB Auto-Refresh**: Periodic updates from central knowledge base

---

## 📊 Architecture Diagram

```
┌─────────────────────────────────────────────┐
│            User Input (CLI)                 │
└────────────────┬────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │  LangGraph (State Machine) │
    ├────────────────────────────┤
    │                            │
    │  ┌──────────────────────┐  │
    │  │  chatbot_node        │  │
    │  │  (1st line support)  │  │
    │  └──────────────────────┘  │
    │           ▼                │
    │  ┌──────────────────────┐  │
    │  │ KB Search (Vector)   │  │
    │  │ ChromaDB + OpenAI    │  │
    │  └──────────────────────┘  │
    │           ▼                │
    │  ┌──────────────────────┐  │
    │  │ Routing Logic        │  │
    │  │ (Conditional Edges)  │  │
    │  └──────────────────────┘  │
    │           ▼                │
    │  ┌──────────────────────┐  │
    │  │ ticket_collection    │  │
    │  │ (Form Filling)       │  │
    │  └──────────────────────┘  │
    │           ▼                │
    │  ┌──────────────────────┐  │
    │  │ ticket_preview       │  │
    │  │ (Display)            │  │
    │  └──────────────────────┘  │
    │           ▼                │
    │  ┌──────────────────────┐  │
    │  │ ticket_confirmation  │  │
    │  │ (Finalize)           │  │
    │  └──────────────────────┘  │
    │           ▼                │
    │  ┌──────────────────────┐  │
    │  │ submit_ticket        │  │
    │  │ (Success)            │  │
    │  └──────────────────────┘  │
    │                            │
    └────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │   State Checkpointer       │
    │   (MemorySaver)            │
    │   Per thread_id            │
    └────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │   LLM Responses            │
    │   (GPT-4o-mini)            │
    │   + Structured Tool Calls  │
    └────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │   Console Output           │
    │   (User Sees Results)      │
    └────────────────────────────┘
```

---

## 🔐 Security & Configuration

### Environment Variables
Create `.env` file:
```
OPENAI_API_KEY=sk-xxxx...
```

### Data Persistence
- Vector DB stored in `chroma_db/` directory
- Thread-specific state maintained in memory
- No sensitive data stored (can be extended)

### Production Considerations
- Add authentication for API endpoints
- Implement rate limiting
- Add audit logging
- Encrypt sensitive data
- Validate user inputs
- Use environment-specific configs

---

## 📚 References

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [ChromaDB Documentation](https://docs.trychroma.com/)
- [OpenAI API Reference](https://platform.openai.com/docs/api-reference)
- [LangChain Documentation](https://python.langchain.com/)

---

## 📄 Summary

The **Ticket Agent** is a sophisticated multi-stage chatbot that combines conversational AI with knowledge base integration to provide efficient first-line IT support and ticket creation. It uses LangGraph for state management, ChromaDB for semantic search, and OpenAI's GPT-4o-mini for intelligent responses. The system handles complex user interactions through multiple phases while maintaining stateful conversation history and preventing common UI anti-patterns like auto-population of form fields.
