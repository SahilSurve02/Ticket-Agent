# Complete User Journey: From Conversation to Ticket Creation

## Presentation Guide: End-to-End Ticket Creation Flow

**Target Audience**: Technical presentation  
**Duration**: 15-20 minutes  
**Coverage**: Conceptual + Code-level implementation

---

## Table of Contents
1. [Journey Overview](#journey-overview)
2. [Step-by-Step Walkthrough](#step-by-step-walkthrough)
3. [Architecture Components](#architecture-components)
4. [Code Flow Details](#code-flow-details)
5. [LLM Calls & Decisions](#llm-calls--decisions)

---

## Journey Overview

### User Story
```
Krishna is having WiFi issues on his laptop. He chats with the bot,
tries the suggested solutions, they don't work completely, so he
creates a support ticket and edits the priority before submitting.
```

### High-Level Flow Diagram
```
┌─────────────┐
│   START     │
│ User enters │──┐
│  chatbot    │  │
└─────────────┘  │
                 ▼
        ┌────────────────┐
        │  1. GREETING   │
        │  (Chatbot Node)│
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  2. DESCRIBE   │
        │     ISSUE      │──→ KB Search (LLM)
        │  (Chatbot Node)│
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  3. TRY STEPS  │
        │   (User tries) │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  4. DIDN'T     │
        │     WORK       │──→ Offer Ticket
        │  (Chatbot Node)│
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  5. CONFIRM    │
        │  "Yes, create" │──→ Handoff to Ticket Agent
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  6. COLLECT    │
        │  TICKET INFO   │──→ Category, Device, Priority, etc.
        │(Ticket Agent)  │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  7. PREVIEW    │
        │    TICKET      │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  8. EDIT       │
        │   Priority     │──→ LLM extracts changes
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  9. CONFIRM    │──→ Router decides: submit/edit/cancel
        │   & SUBMIT     │
        └────────┬───────┘
                 │
                 ▼
        ┌────────────────┐
        │  10. TICKET    │
        │    CREATED     │
        │  (Saved to DB) │
        └────────────────┘
```

---

## Step-by-Step Walkthrough

### **STEP 1: Initial Greeting**

#### 👤 User Action
```
User: "Hi"
```

#### 🤖 What Happens (Conceptual)

1. **Input Processing**: Message enters the system
2. **Scope Validation**: Check if request is in scope
3. **Node Routing**: Route to Chatbot Node
4. **Response Generation**: Friendly greeting

#### 💻 Code Flow

**File**: `main.py` → `run_chat()` → Graph execution

```python
# main.py, line 257
user_text = input("You: ").strip()

# Create HumanMessage
state_update = {
    "messages": [HumanMessage(content=user_text)]
}

# Execute graph
for event in graph.stream(state_update, thread):
    # Graph routes to chatbot_node
```

**File**: `src/nodes.py` → `chatbot_node()`

```python
# src/nodes.py, line 23
def chatbot_node(state: AgentState):
    """Chatbot node - delegates to ChatbotAgent"""
    agent = get_chatbot_agent()
    return agent.process(state)
```

**File**: `src/agents.py` → `ChatbotAgent.process()`

```python
# src/agents.py, line 38
def process(self, state: AgentState) -> Dict:
    messages = state["messages"]
    user_message = messages[-1].content  # "Hi"
    
    # Step 0: Scope validation
    if len(messages) <= 2:
        is_in_scope = self._check_it_scope(user_message)
```

#### 🔍 LLM CALL #1: Scope Validation

**Purpose**: Determine if "Hi" is in scope or other-domain request

**File**: `src/agents.py` → `_check_it_scope()`

```python
# src/agents.py, line 197
def _check_it_scope(self, user_message: str) -> bool:
    system_prompt = """You are a domain classifier...
    Greetings and casual conversation → ALLOW (respond "YES")
    """
    
    response = self.llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=f"User request: {user_message}")
    ])
    
    # LLM Response: "YES"
    result = response.content.strip().upper()
    is_it_related = "YES" in result
    # Returns: True (allowed)
```

**LLM Model**: GPT-4o-mini  
**Input Tokens**: ~250  
**Output**: "YES"  
**Result**: ✅ Allowed to proceed

#### 💬 Response Generation

Since it's a simple greeting, no KB search needed:

```python
# src/agents.py, line 178
system_prompt = """You are the IT Support Chatbot Agent.
Your role: Provide clear troubleshooting steps..."""

response = self.llm.invoke([SystemMessage(content=system_prompt)] + messages)
# Response: "Hello! How can I assist you today?"
```

#### 🔍 LLM CALL #2: Generate Greeting Response

**Model**: GPT-4o-mini  
**Input**: System prompt + conversation history  
**Output**: "Hello! How can I assist you today?"

#### 🔀 Router Decision

**File**: `src/router.py` → `route_from_chatbot()`

```python
# src/router.py, line 82
def route_from_chatbot(messages, last_question, ...):
    # Check deterministic states first
    if awaiting_ticket_confirmation:
        return END  # Wait for user
    
    # No handoff signal detected
    # Use LLM-based routing
    return self._llm_route_chatbot(messages)
```

#### 🔍 LLM CALL #3: Route Decision

```python
# src/router.py, line 164
def _llm_route_chatbot(self, messages):
    routing_prompt = """Analyze the conversation and decide next action.
    
    ROUTING OPTIONS:
    1. "continue_chat" - Continue troubleshooting
    2. "ticket_collection" - Hand off to ticket creation
    3. "end" - Wait for user input
    """
    
    decision = self.router_llm.invoke([SystemMessage(content=routing_prompt)])
    # Decision: "end" (conversation just started, wait for user)
```

**Output**: `END` → Wait for next user input

#### 📤 Bot Response
```
Bot: "Hello! How can I assist you today?"
```

---

### **STEP 2: User Describes Issue**

#### 👤 User Action
```
User: "I am facing some issues with my laptop can u help me with that"
```

#### 🤖 What Happens (Conceptual)

1. **Scope Check**: Passed (conversation already started, skips scope)
2. **Category Detection**: Keyword-based classification
3. **Knowledge Base Search**: Semantic search with embeddings
4. **Response**: Ask for more details

#### 💻 Code Flow

**File**: `src/agents.py` → `ChatbotAgent.process()`

```python
# Skip scope check (len(messages) = 4, > 2)
# Already in conversation

# Detect category
detected_cat = detect_category(user_message)
```

**File**: `src/kb.py` → `detect_category()`

```python
# src/kb.py, line 288
def detect_category(message: str) -> Optional[str]:
    message_lower = message.lower()
    
    # Check IT categories
    categories = {
        "Hardware": ["laptop", "computer", "slow", "performance", ...],
        ...
    }
    
    # "laptop" found → "Hardware"
    return "Hardware"
```

**Result**: Category = "Hardware"

#### 🔍 Knowledge Base Search

**File**: `src/agents.py` → calls `get_best_solution()`

```python
# src/agents.py, line 125
kb_results = get_best_solution(
    kb=kb,
    issue_description=user_message,
    conversation_history=[m.content for m in messages[:-1]],
    category="Hardware"
)
```

**File**: `src/kb.py` → `get_best_solution()`

```python
# src/kb.py, line 158
def get_best_solution(kb, issue_description, conversation_history, category):
    # Strategy 1: Direct semantic search
    results = search_knowledge(kb, issue_description, category, top_k=3)
    
    if results and results[0]["similarity"] >= 0.4:
        return {"found": True, "confidence": "high", ...}
    # Continue with fallback strategies...
```

**File**: `src/kb.py` → `search_knowledge()`

```python
# src/kb.py, line 102
def search_knowledge(kb, query, category, top_k=3):
    # Perform similarity search using ChromaDB + OpenAI embeddings
    results = kb.vectorstore.similarity_search_with_score(
        query=query,
        k=top_k,
        filter={"category": category} if category else None
    )
    
    # Convert L2 distance to similarity score
    # L2_dist=1.3844 → similarity=0.4194
```

#### 🔍 LLM CALL #4: Embedding Generation

**Model**: OpenAI `text-embedding-3-small`  
**Input**: "I am facing some issues with my laptop can u help me with that"  
**Output**: 1536-dimensional vector  
**Purpose**: Vector similarity search in ChromaDB

**KB Search Results**:
```
[DEBUG] KB result: L2_dist=1.3844, similarity=0.4194
[DEBUG] KB result: L2_dist=1.4349, similarity=0.4107
```

**Confidence**: Medium (0.4194 < 0.4, but close)

#### 📊 Decision Logic

```python
# src/agents.py, line 136
# Check if user wants ticket
wants_ticket_explicit = any(phrase in user_message.lower() for phrase in [
    "create ticket", "file ticket", ...
])
# Result: False (user just describing issue)

solution_failed = any(phrase in user_message.lower() for phrase in [
    "didn't work", "still not working", ...
]) and len(messages) > 2
# Result: False (not indicating failure)

# Don't ask for ticket yet
```

#### 🔍 LLM CALL #5: Generate Response

```python
# src/agents.py, line 178
system_prompt = """You are the IT Support Chatbot Agent.
No specific KB solution found, ask for more details."""

response = self.llm.invoke([SystemMessage(content=system_prompt)] + messages)
```

**Model**: GPT-4o-mini  
**Output**: "Of course! Please describe the issue you're experiencing with your laptop."

#### 📤 Bot Response
```
Bot: "Of course! Please describe the issue you're experiencing with your laptop."
```

---

### **STEP 3: User Provides Specific Details**

#### 👤 User Action
```
User: "My Dell Laptop's wifi and connectivity is not working well"
```

#### 🤖 What Happens (Conceptual)

1. **Category Detection**: "Network" (WiFi keyword)
2. **KB Search**: HIGH confidence match found
3. **Solution Presentation**: Show troubleshooting steps
4. **No Ticket Offer**: User hasn't tried solution yet

#### 💻 Code Flow

**File**: `src/kb.py` → `detect_category()`

```python
# src/kb.py, line 288
message_lower = "my dell laptop's wifi and connectivity is not working well"

categories = {
    "Network": ["wifi", "wireless", "internet", "connection", ...],
    ...
}

# "wifi" found → Category = "Network"
```

**Result**: Category = "Network"

#### 🔍 KB Search with High Confidence

```python
# src/kb.py → search_knowledge()
query = "My Dell Laptop's wifi and connectivity is not working well"
category = "Network"

# Vector similarity search
results = kb.vectorstore.similarity_search_with_score(
    query=query,
    k=3,
    filter={"category": "Network"}
)
```

#### 🔍 LLM CALL #6: Embedding for KB Search

**Model**: `text-embedding-3-small`  
**Input**: "My Dell Laptop's wifi and connectivity is not working well"  
**Output**: 1536-dim vector

**Search Results**:
```
[DEBUG] KB result: L2_dist=1.0024, similarity=0.4994  ← HIGH!
[DEBUG] KB result: L2_dist=1.1744, similarity=0.4599
```

**Best Match**: "WiFi Connection Drops Intermittently" (0.4994 similarity)

**KB Document Found**:
```json
{
  "title": "WiFi Connection Drops Intermittently",
  "category": "Network",
  "solution": "1. Update WiFi drivers from Device Manager\n2. Change WiFi channel on router (1, 6, or 11 for 2.4GHz)\n3. Disable power saving for WiFi adapter\n4. Reset network settings: netsh winsock reset\n5. Update router firmware",
  "severity": "Medium"
}
```

**Confidence**: **HIGH** (0.4994 ≥ 0.4)

#### 📊 Ticket Decision Logic

```python
# src/agents.py, line 136
user_message = "My Dell Laptop's wifi and connectivity is not working well"

# Check explicit ticket request
wants_ticket_explicit = any(phrase in user_message.lower() for phrase in [
    "create ticket", "file ticket", "escalate", ...
])
# Result: False ✓

# Check if solution failed (NEW LOGIC)
solution_failed = any(phrase in user_message.lower() for phrase in [
    "didn't work", "doesn't work", "still not working", ...
]) and len(messages) > 2
# Result: False ✓ (no failure phrases)

# GOOD! Don't ask for ticket, show KB solution instead
```

#### 🔍 LLM CALL #7: Generate Solution Response

```python
# src/agents.py, line 161
kb_context = """
**Solution** (Relevance: 50%):
Title: WiFi Connection Drops Intermittently
Category: Network
Solution: 
1. Update WiFi drivers from Device Manager
2. Change WiFi channel on router (1, 6, or 11 for 2.4GHz)
3. Disable power saving for WiFi adapter
4. Reset network settings: netsh winsock reset
5. Update router firmware
"""

system_prompt = f"""You are the IT Support Chatbot Agent.

KNOWLEDGE BASE SOLUTIONS:
{kb_context}

YOUR ROLE:
1. Provide clear troubleshooting steps from the knowledge base.
2. Format as numbered list
3. Ask: "Let me know if this helps!"
"""

response = self.llm.invoke([
    SystemMessage(content=system_prompt)
] + messages)
```

**Model**: GPT-4o-mini  
**Input**: System prompt with KB solution + conversation  
**Output**: Formatted troubleshooting steps

#### 📤 Bot Response
```
Bot: "I can help you with that WiFi issue! Here are some troubleshooting steps:

1. **Update WiFi drivers**: 
   - Open Device Manager
   - Find Network Adapters → Your WiFi adapter
   - Right-click → Update driver

2. **Reset network settings**:
   - Open Command Prompt as Administrator
   - Run: netsh winsock reset
   - Restart your laptop

3. **Check power settings**:
   - Device Manager → WiFi adapter → Properties
   - Power Management tab
   - Uncheck "Allow computer to turn off this device"

4. **Router settings**:
   - Change WiFi channel to 1, 6, or 11
   - Update router firmware if needed

Let me know if this helps!"
```

---

### **STEP 4: User Indicates Solution Didn't Work**

#### 👤 User Action
```
User: "I tried the steps but it's still not working properly"
```

#### 🤖 What Happens (Conceptual)

1. **Failure Detection**: Keywords "tried" + "still not working"
2. **Conversation History Check**: len(messages) > 2 ✓
3. **Decision**: Offer ticket creation
4. **State Update**: Set `awaiting_ticket_confirmation = True`

#### 💻 Code Flow

**File**: `src/agents.py` → `ChatbotAgent.process()`

```python
# src/agents.py, line 136
user_message = "I tried the steps but it's still not working properly"

# Check explicit ticket request
wants_ticket_explicit = False  # No "create ticket" phrase

# Check if solution failed
solution_failed = any(phrase in user_message.lower() for phrase in [
    "didn't work", "doesn't work", "tried that", "still not working", ...
]) and len(messages) > 2

# "tried" found ✓
# "still not working" found ✓
# len(messages) = 8 > 2 ✓
# Result: True!
```

#### 📊 Decision

```python
# src/agents.py, line 149
if is_ambiguous_feedback or wants_ticket_explicit or solution_failed:
    msg = "Would you like me to create a support ticket for this issue? I can help you file it with our support team. (yes/no)"
    
    return {
        "messages": [AIMessage(content=msg)],
        "detected_category": "Network",  # Preserved from earlier
        "awaiting_ticket_confirmation": True  # Important!
    }
```

#### 🔀 Router Decision

```python
# src/router.py, line 108
def route_from_chatbot(...):
    # Check awaiting_ticket_confirmation
    if awaiting_ticket_confirmation:
        print("→ ROUTE: END (awaiting ticket confirmation)")
        return ChatbotRoute.END
```

**Result**: END (wait for user's yes/no answer)

#### 📤 Bot Response
```
Bot: "Would you like me to create a support ticket for this issue? 
      I can help you file it with our support team. (yes/no)"
```

**State After This Step**:
```python
{
    "messages": [...all previous messages...],
    "detected_category": "Network",
    "awaiting_ticket_confirmation": True,  ← KEY!
    "kb_used": True,
    "kb_confidence": "high"
}
```

---

### **STEP 5: User Confirms Ticket Creation**

#### 👤 User Action
```
User: "yes"
```

#### 🤖 What Happens (Conceptual)

1. **Confirmation Check**: State has `awaiting_ticket_confirmation = True`
2. **Parse Response**: "yes" detected
3. **Handoff Signal**: Generate "HANDOFF_TO_TICKET_AGENT" message
4. **Pre-fill Data**: Try to extract device, priority from conversation
5. **Router**: Detect handoff → Route to `ticket_collection`

#### 💻 Code Flow

**File**: `src/agents.py` → `ChatbotAgent.process()`

```python
# src/agents.py, line 47
def process(self, state: AgentState) -> Dict:
    awaiting_ticket_confirmation = state.get("awaiting_ticket_confirmation", False)
    
    # Handle ticket creation confirmation
    if awaiting_ticket_confirmation:  # True!
        response_lower = user_message.lower().strip()  # "yes"
        
        # User confirms ticket creation
        if any(word in response_lower for word in ["yes", "yeah", "yep", "sure", ...]):
```

#### 🧠 Intelligent Pre-filling

```python
# src/agents.py, line 52
prefill = {}
try:
    user_devices = state.get("user_devices", [])  # ["Dell-Laptop-001", ...]
    convo_text = " ".join([m.content for m in messages[-3:]]).lower()
    # "...my dell laptop's wifi...tried the steps...yes"
    
    # Detect device by matching tokens
    for device in user_devices:
        dev_lower = device.lower()  # "dell-laptop-001"
        if dev_lower in convo_text or any(tok in convo_text for tok in dev_lower.split()):
            # "dell" in convo_text ✓
            prefill["device_id"] = device  # "Dell-Laptop-001"
            break
    
    # Detect priority
    priority_map = {
        "critical": "Critical",
        "high": "High", "urgent": "High",
        "medium": "Medium",
        "low": "Low"
    }
    
    # No priority words in conversation
    # Don't pre-fill priority (will ask user)
    
except Exception:
    prefill = {}

# Result: prefill = {"device_id": "Dell-Laptop-001"}
```

#### 📦 Create Handoff Message

```python
# src/agents.py, line 87
msg = "I'll transfer you to our Ticket Agent to create a support ticket.\n\nHANDOFF_TO_TICKET_AGENT"

ticket_obj = state.get("ticket") or create_empty_ticket()
ticket_obj = ticket_obj.model_copy(update=prefill)
# ticket_obj.device_id = "Dell-Laptop-001"

return {
    "messages": [AIMessage(content=msg)],
    "awaiting_ticket_confirmation": False,  # Reset!
    "ticket": ticket_obj
}
```

#### 🔀 Router Detects Handoff

**File**: `src/router.py` → `route_from_chatbot()`

```python
# src/router.py, line 149
last_msg = messages[-1]  # AIMessage from above
last_content = last_msg.content

# Check for explicit handoff signals
if "HANDOFF_TO_TICKET_AGENT" in last_content:
    print("→ ROUTE: TICKET_COLLECTION (handoff signal detected)")
    return ChatbotRoute.TICKET_COLLECTION  # ← KEY!
```

#### 🎯 Graph Routes to Ticket Collection Node

**File**: `main.py` → Graph definition

```python
# main.py, line 139
graph_builder.add_edge("chatbot", "route_chatbot")

def conditional_route_chatbot(state):
    route = router.route_from_chatbot(...)
    # Returns: ChatbotRoute.TICKET_COLLECTION
    return route.value  # "ticket_collection"

graph_builder.add_conditional_edges(
    "route_chatbot",
    conditional_route_chatbot,
    {
        "ticket_collection": "ticket_collection",  # ← Goes here!
        "end": END,
        ...
    }
)
```

#### 📤 Bot Response
```
Bot: "I'll transfer you to our Ticket Agent to create a support ticket.

HANDOFF_TO_TICKET_AGENT"
```

**State Now**:
```python
{
    "messages": [...],
    "detected_category": "Network",
    "awaiting_ticket_confirmation": False,
    "ticket": {
        "device_id": "Dell-Laptop-001",  # Pre-filled!
        "category": null,
        "priority": null,
        "description": null,
        ...
    }
}
```

---

### **STEP 6: Ticket Information Collection**

#### 🎫 Ticket Agent Takes Over

**Node**: `ticket_collection_node`

#### 💻 Code Flow

**File**: `src/nodes.py` → `ticket_collection_node()`

```python
# src/nodes.py, line 51
def ticket_collection_node(state: AgentState):
    """Ticket collection node - delegates to TicketAgent"""
    agent = get_ticket_agent()
    return agent.process_ticket_collection(state)
```

**File**: `src/agents.py` → `TicketAgent.process_ticket_collection()`

```python
# src/agents.py, line 254
def process_ticket_collection(self, state: AgentState) -> Dict:
    current_ticket = state["ticket"]
    # current_ticket.device_id = "Dell-Laptop-001" (pre-filled)
    
    # Get last user message
    messages = state["messages"]
    last_user_message = ""
    for m in reversed(messages):
        if isinstance(m, HumanMessage):
            last_user_message = m.content  # "yes"
            break
    
    # Check for missing fields
    return self._ask_next_field(current_ticket, user_devices, ...)
```

#### 📝 Field Collection Logic

**File**: `src/agents.py` → `_ask_next_field()`

```python
# src/agents.py, line 431
def _ask_next_field(self, ticket, user_devices, extra_field_index, state):
    # Required core fields
    required = ["category", "device_id", "priority", "description"]
    
    # Check which field is missing
    if not ticket.category:
        # Ask for category
        detected_category = state.get("detected_category")  # "Network"!
        
        if detected_category and detected_category != "General":
            # Auto-fill from earlier detection!
            ticket = ticket.model_copy(update={"category": detected_category})
            # Continue to next field
```

**Category Auto-filled**: "Network" (from Step 3!)

```python
    # Category filled, check device
    if not ticket.device_id:
        # Ask for device
        # But it's already filled! ("Dell-Laptop-001")
        pass
    
    # Device filled, check priority
    if not ticket.priority:
        msg = """What is the priority of this issue?
        
        1. Low - Can wait, minor inconvenience
        2. Medium - Affecting work but have workaround
        3. High - Blocking work, need urgent help
        4. Critical - System down, business stopped
        
        Please enter 1-4 or type the priority name:"""
        
        return {
            "messages": [AIMessage(content=msg)],
            "last_question": "priority"  # Track what we asked
        }
```

#### 📤 Bot Response (First Question)
```
Bot: "What is the priority of this issue?

1. Low - Can wait, minor inconvenience
2. Medium - Affecting work but have workaround  
3. High - Blocking work, need urgent help
4. Critical - System down, business stopped

Please enter 1-4 or type the priority name:"
```

**State After**:
```python
{
    "last_question": "priority",
    "ticket": {
        "category": "Network",     # Auto-filled
        "device_id": "Dell-Laptop-001",  # Pre-filled
        "priority": null,          # Waiting for answer
        "description": null,
        ...
    }
}
```

---

#### 👤 User Answers: Priority

```
User: "2"
```

#### 💻 Processing Answer

**File**: `src/agents.py` → `_process_user_response()`

```python
# src/agents.py, line 338
def _process_user_response(self, ticket, last_question, user_msg, ...):
    # Priority selection
    if last_question == "priority":
        priority_map = {
            "1": "Low", "2": "Medium", "3": "High", "4": "Critical",
            "low": "Low", "medium": "Medium", "high": "High", ...
        }
        matched = priority_map.get(user_msg.lower().strip(), "Medium")
        # "2" → "Medium"
        
        ticket = ticket.model_copy(update={"priority": "Medium"})
        return ticket, None, extra_idx  # Clear last_question
```

**Ticket Updated**: `priority = "Medium"`

#### 📝 Next Field: Description

```python
# src/agents.py, line 467
if not ticket.description:
    # Use conversation context to suggest description
    convo_summary = " ".join([m.content for m in messages[-6:-1]])
    # "...my dell laptop's wifi and connectivity is not working well...tried steps..."
    
    msg = f"""Please describe the issue in detail.

Based on our conversation, I can suggest:
"{convo_summary[:200]}..."

You can:
- Press Enter to use this description
- Or type your own description:"""
    
    return {
        "messages": [AIMessage(content=msg)],
        "last_question": "description"
    }
```

#### 📤 Bot Response
```
Bot: "Please describe the issue in detail.

Based on our conversation, I can suggest:
'My Dell Laptop's wifi and connectivity is not working well. 
I tried updating drivers and resetting network settings but 
the issue persists...'

You can:
- Press Enter to use this description
- Or type your own description:"
```

---

#### 👤 User Provides Description

```
User: [presses Enter]
```

or

```
User: "WiFi keeps disconnecting every few minutes on my Dell laptop"
```

#### 💻 Processing Description

```python
# src/agents.py, line 359
if last_question == "description":
    if not user_msg or user_msg.strip() == "":
        # User pressed Enter, use suggested
        suggested = " ".join([m.content for m in messages[-6:-2]])
        ticket = ticket.model_copy(update={"description": suggested[:500]})
    else:
        # User typed custom description
        ticket = ticket.model_copy(update={"description": user_msg})
    
    return ticket, None, extra_idx
```

#### 📝 Check for Extra Fields

```python
# src/agents.py, line 431
# Core fields all filled!
# Check category-specific extra fields

category = ticket.category  # "Network"
template = FORM_TEMPLATES.get(category)

# src/state.py, line 12
FORM_TEMPLATES = {
    "Network": {
        "extra_fields": ["connection_type", "error_message"],
        "field_prompts": {
            "connection_type": "What type of connection...?",
            "error_message": "Are you seeing any error messages?"
        }
    }
}

required_extras = ["connection_type", "error_message"]
```

#### 📤 Bot Asks for Extra Field 1

```
Bot: "What type of connection are you having issues with?
  • WiFi
  • Ethernet/Wired
  • VPN"
```

---

#### 👤 User Answers Extra Fields

```
User: "WiFi"
User: "No error messages"
```

**Processing**: Same `_process_user_response()` flow, stores in `ticket.extra_fields`

```python
ticket.extra_fields = {
    "connection_type": "WiFi",
    "error_message": "No error messages"
}
```

---

#### ✅ All Fields Collected!

```python
# src/agents.py, line 514
# All core + extra fields filled
# Generate ticket summary

return {
    "messages": [AIMessage(content="Collecting ticket information...")],
    "ticket_collection_complete": True  # Signal we're done!
}
```

#### 🔀 Router Decision

**File**: `src/router.py` → `route_ticket_collection()`

```python
# src/router.py, line 260
def route_ticket_collection(state):
    if state.get("ticket_collection_complete"):
        return TicketCollectionRoute.TICKET_PREVIEW  # ← Go to preview!
    
    # Check if all fields filled
    # ...
    return TicketCollectionRoute.TICKET_PREVIEW
```

**Route**: → `ticket_preview`

---

### **STEP 7: Ticket Preview**

#### 💻 Code Flow

**File**: `src/nodes.py` → `ticket_preview_node()`

```python
# src/nodes.py, line 61
def ticket_preview_node(state: AgentState):
    """Show ticket preview and ask for confirmation"""
    ticket = state["ticket"]
    
    # Format ticket for display
    preview = f"""
╔══════════════════════════════════════════════════════════╗
║                    TICKET PREVIEW                        ║
╚══════════════════════════════════════════════════════════╝

📋 Ticket ID: {ticket.ticket_id}
👤 Requester: {ticket.requester_email}

📁 Category: {ticket.category}
💻 Device: {ticket.device_id}
🔥 Priority: {ticket.priority}

📝 Description:
{ticket.description}

🔧 Additional Information:
   - Connection Type: {ticket.extra_fields.get('connection_type')}
   - Error Message: {ticket.extra_fields.get('error_message')}

📅 Created: {ticket.created_at}
📊 Status: {ticket.status}

─────────────────────────────────────────────────────────────
"""
    
    msg = preview + "\n\n**Actions**: Type 'submit' to create, 'edit' to modify, or 'cancel' to discard"
    
    return {
        "messages": [AIMessage(content=msg)],
        "awaiting_confirmation": True  # Important!
    }
```

#### 📤 Bot Response
```
Bot: "
╔══════════════════════════════════════════════════════════╗
║                    TICKET PREVIEW                        ║
╚══════════════════════════════════════════════════════════╝

📋 Ticket ID: TKT-20251222-7A3F
👤 Requester: krishna.ronaldo@company.com

📁 Category: Network
💻 Device: Dell-Laptop-001
🔥 Priority: Medium

📝 Description:
My Dell Laptop's wifi and connectivity is not working well. 
I tried updating drivers and resetting network settings but 
the issue persists.

🔧 Additional Information:
   - Connection Type: WiFi
   - Error Message: No error messages

📅 Created: 2025-12-22 14:30:00
📊 Status: Open

─────────────────────────────────────────────────────────────

**Actions**: Type 'submit' to create, 'edit' to modify, or 'cancel' to discard"
```

**State**:
```python
{
    "awaiting_confirmation": True,
    "ticket": {<fully filled ticket>},
    ...
}
```

---

### **STEP 8: User Requests Edit**

#### 👤 User Action
```
User: "edit"
```

#### 💻 Code Flow

**File**: `src/router.py` → `route_from_chatbot()`

Since we're in `awaiting_confirmation` state:

```python
# src/router.py, line 113
if awaiting_confirmation:
    print("→ ROUTE: TICKET_CONFIRMATION")
    return ChatbotRoute.TICKET_CONFIRMATION  # Route to confirmation handler
```

**File**: `src/nodes.py` → `ticket_confirmation_node()`

```python
# src/nodes.py, line 102
def ticket_confirmation_node(state: AgentState):
    """Handle user's confirmation action (submit/edit/cancel)"""
    
    # Get last user message
    last_user_message = ...  # "edit"
    
    # Use router to determine action
    router = get_router()
    action = router.route_confirmation(last_user_message)
```

#### 🔍 LLM CALL #8: Parse Confirmation Action

**File**: `src/router.py` → `route_confirmation()`

```python
# src/router.py, line 222
def route_confirmation(self, user_message: str) -> ConfirmationRoute:
    routing_prompt = f"""Analyze user's response to ticket confirmation.
    
    USER'S RESPONSE: "{user_message}"  # "edit"
    
    What is the user's intent?
    - "submit_ticket" - Submit/confirm
    - "edit" - Modify ticket details
    - "cancel" - Cancel ticket
    - "invalid" - Unclear response
    """
    
    decision = self.router_llm.invoke([SystemMessage(content=routing_prompt)])
```

**Model**: GPT-4o-mini  
**Output**: 
```python
RouterDecision(
    route="edit",
    confidence=1.0,
    reasoning="User explicitly said 'edit'"
)
```

#### 📝 Edit Mode Activated

```python
# src/nodes.py, line 102
if action == ConfirmationRoute.EDIT:
    msg = """Sure! What would you like to change?

You can modify:
- Category
- Device
- Priority (current: Medium)
- Description
- Additional details

Example: "Change priority to High" or "Update description to include error code"
"""
    
    return {
        "messages": [AIMessage(content=msg)],
        "edit_mode": True,  # ← KEY!
        "awaiting_confirmation": False,
        "confirmation_action": "edit"
    }
```

#### 📤 Bot Response
```
Bot: "Sure! What would you like to change?

You can modify:
- Category
- Device  
- Priority (current: Medium)
- Description
- Additional details

Example: 'Change priority to High' or 'Update description to include error code'"
```

---

#### 👤 User Specifies Edit

```
User: "Change priority to High"
```

#### 💻 Code Flow

**File**: `src/router.py` → `route_from_chatbot()`

```python
# src/router.py, line 105
if edit_mode:  # True!
    print("→ ROUTE: TICKET_COLLECTION (edit mode)")
    return ChatbotRoute.TICKET_COLLECTION
```

**Routes back to**: `ticket_collection_node` → `TicketAgent`

**File**: `src/agents.py` → `TicketAgent.process_ticket_collection()`

```python
# src/agents.py, line 263
is_edit_mode = state.get("edit_mode", False)  # True!

if is_edit_mode:
    print(f"[TicketAgent] Processing edit request: {last_user_message}")
    
    # Get available devices for context
    user_devices = state.get("user_devices", [])
    devices_list = ", ".join(user_devices)
```

#### 🔍 LLM CALL #9: Extract Edit Changes

```python
# src/agents.py, line 271
edit_prompt = f"""You are an editing assistant. 
The user wants to change ticket details.

Based on their request, identify the fields to update and new values.
Use the TicketSchema tool to apply these changes.

**AVAILABLE DEVICES:** {devices_list}

**IMPORTANT:**
- Use correct top-level fields for 'category', 'device_id', 'priority', 'description'
- Do NOT place core fields inside 'extra_fields'
- Map priority to: "Low", "Medium", "High", "Critical"

Return the updated fields only.
"""

# LLM with structured output (TicketSchema)
response = self.llm_with_tools.invoke([
    SystemMessage(content=edit_prompt),
    HumanMessage(content=last_user_message)  # "Change priority to High"
])
```

**Model**: GPT-4o-mini with `bind_tools([TicketSchema])`  
**Input**: "Change priority to High"  
**Output (Structured)**:
```python
{
    "tool_calls": [{
        "args": {
            "priority": "High"  # Only changed field
        }
    }]
}
```

#### 🔄 Apply Changes

```python
# src/agents.py, line 286
updated_ticket = current_ticket
if response.tool_calls:
    new_data = response.tool_calls[0]['args']
    # new_data = {"priority": "High"}
    
    # Filter out None values
    new_data = {k: v for k, v in new_data.items() if v is not None}
    
    updated_ticket = current_ticket.model_copy(update=new_data)
    # ticket.priority: "Medium" → "High" ✓

# Return to preview with updated ticket
return {
    "messages": [AIMessage(content="I've updated the ticket. Here's the revised preview...")],
    "ticket": updated_ticket,
    "edit_mode": False,  # Exit edit mode
    "confirmation_action": None,
    "ticket_collection_complete": True  # Go back to preview
}
```

#### 🔀 Router

```python
# route_ticket_collection() sees ticket_collection_complete=True
# Routes to: ticket_preview
```

**Back to Step 7**: Shows updated preview with `Priority: High`

---

### **STEP 9: User Submits Ticket**

#### 👤 User Action
```
User: "submit"
```

#### 💻 Code Flow

**File**: `src/router.py` → `route_confirmation()`

```python
# LLM parses "submit"
RouterDecision(
    route="submit_ticket",
    confidence=1.0,
    reasoning="User wants to submit"
)
```

**File**: `src/nodes.py` → `ticket_confirmation_node()`

```python
# src/nodes.py, line 120
if action == ConfirmationRoute.SUBMIT:
    # Clear confirmation state, proceed to submit
    return {
        "confirmation_action": "submit",
        "awaiting_confirmation": False
    }
```

#### 🔀 Router to Submit Node

**File**: `main.py` → Graph edges

```python
# main.py, line 175
def route_after_confirmation(state):
    action = state.get("confirmation_action")
    
    if action == "submit":
        return "submit_ticket"  # ← Go here!
    elif action == "edit":
        return "ticket_collection"
    else:
        return END

graph_builder.add_conditional_edges(
    "ticket_confirmation",
    route_after_confirmation,
    {
        "submit_ticket": "submit_ticket",
        ...
    }
)
```

---

### **STEP 10: Ticket Submission**

#### 💻 Code Flow

**File**: `src/nodes.py` → `submit_ticket_node()`

```python
# src/nodes.py, line 140
def submit_ticket_node(state: AgentState):
    """Submit the ticket to the ticketing system"""
    ticket = state["ticket"]
    
    # Finalize ticket
    final_ticket = ticket.model_copy(update={
        "status": "Submitted",
        "submitted_at": datetime.now().isoformat()
    })
    
    # Save to database (JSON file for demo)
    save_ticket_to_db(final_ticket)
    
    # Generate confirmation message
    msg = f"""
✅ **Ticket Successfully Created!**

📋 Ticket ID: {final_ticket.ticket_id}
📁 Category: {final_ticket.category}
🔥 Priority: {final_ticket.priority}
📧 Confirmation sent to: {final_ticket.requester_email}

Your ticket has been submitted to our support team.
You'll receive updates via email.

Is there anything else I can help you with?
"""
    
    return {
        "messages": [AIMessage(content=msg)],
        "ticket": final_ticket,
        "ticket_submitted": True
    }
```

#### 💾 Save to Database

**File**: `src/nodes.py` → `save_ticket_to_db()`

```python
# src/nodes.py, line 175
def save_ticket_to_db(ticket: TicketSchema):
    import json
    from pathlib import Path
    
    # Load existing tickets
    tickets_file = Path("data/tickets.json")
    
    if tickets_file.exists():
        with open(tickets_file, 'r') as f:
            tickets = json.load(f)
    else:
        tickets = []
    
    # Add new ticket
    ticket_dict = ticket.model_dump()
    tickets.append(ticket_dict)
    
    # Save back to file
    with open(tickets_file, 'w') as f:
        json.dump(tickets, f, indent=2)
    
    print(f"[DB] Ticket {ticket.ticket_id} saved successfully")
```

#### 📤 Bot Response
```
Bot: "
✅ **Ticket Successfully Created!**

📋 Ticket ID: TKT-20251222-7A3F
📁 Category: Network
🔥 Priority: High
📧 Confirmation sent to: krishna.ronaldo@company.com

Your ticket has been submitted to our support team.
You'll receive updates via email.

Is there anything else I can help you with?"
```

#### 📁 Saved to `data/tickets.json`

```json
[
  {
    "ticket_id": "TKT-20251222-7A3F",
    "requester_email": "krishna.ronaldo@company.com",
    "category": "Network",
    "device_id": "Dell-Laptop-001",
    "priority": "High",
    "description": "My Dell Laptop's wifi and connectivity is not working well. I tried updating drivers and resetting network settings but the issue persists.",
    "extra_fields": {
      "connection_type": "WiFi",
      "error_message": "No error messages"
    },
    "status": "Submitted",
    "created_at": "2025-12-22T14:30:00",
    "submitted_at": "2025-12-22T14:35:27"
  }
]
```

---

## Architecture Components

### 1. **LangGraph State Machine**

**File**: `main.py`

```python
# Node definitions
graph_builder.add_node("chatbot", chatbot_node)
graph_builder.add_node("ticket_collection", ticket_collection_node)
graph_builder.add_node("ticket_preview", ticket_preview_node)
graph_builder.add_node("ticket_confirmation", ticket_confirmation_node)
graph_builder.add_node("submit_ticket", submit_ticket_node)

# Routing nodes (decision points)
graph_builder.add_node("route_chatbot", lambda x: x)
graph_builder.add_node("route_ticket_collection", lambda x: x)

# Edges (transitions)
graph_builder.add_edge(START, "chatbot")
graph_builder.add_edge("chatbot", "route_chatbot")

# Conditional edges (based on state)
graph_builder.add_conditional_edges(
    "route_chatbot",
    conditional_route_chatbot,
    {
        "ticket_collection": "ticket_collection",
        "ticket_confirmation": "ticket_confirmation",
        "continue_chat": "chatbot",
        "end": END
    }
)
```

### 2. **State Management**

**File**: `src/state.py`

```python
class AgentState(TypedDict):
    messages: Annotated[List, add_messages]  # Conversation history
    
    # User context
    user_info: Dict
    user_devices: List[str]
    
    # Ticket data
    ticket: TicketSchema
    detected_category: Optional[str]
    
    # Control flags
    awaiting_ticket_confirmation: bool
    awaiting_confirmation: bool
    edit_mode: bool
    ticket_collection_complete: bool
    
    # Tracking
    last_question: Optional[str]
    current_extra_field_index: int
    confirmation_action: Optional[str]
    
    # KB metadata
    kb_used: bool
    kb_confidence: Optional[str]
```

### 3. **Agent Architecture**

#### ChatbotAgent (Troubleshooting)
- **Responsibilities**: Initial interaction, KB search, solution presentation
- **LLM Calls**: Scope check, category detection, response generation
- **Decision Points**: When to offer ticket

#### TicketAgent (Ticket Management)
- **Responsibilities**: Field collection, validation, editing
- **LLM Calls**: Edit parsing, auto-filling
- **Decision Points**: Which field to ask next

### 4. **Knowledge Base System**

**Components**:
- **Vector Store**: ChromaDB with persistence
- **Embeddings**: OpenAI `text-embedding-3-small`
- **Search Strategy**: Multi-tier fallback
  1. Category-filtered semantic search
  2. Global semantic search
  3. Context-enhanced search

**File**: `src/kb.py`

```python
# Embedding generation
embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# Vector store
vectorstore = Chroma(
    collection_name="it_support_kb",
    embedding_function=embeddings,
    persist_directory="./chroma_db"
)

# Similarity search
results = vectorstore.similarity_search_with_score(
    query=user_query,
    k=3,
    filter={"category": "Network"}
)
```

### 5. **Routing System**

**Hybrid Approach**:
1. **Rule-based** (deterministic states)
   - Edit mode → ticket_collection
   - Awaiting confirmation → END
   - Handoff signal → ticket_collection

2. **LLM-based** (ambiguous cases)
   - Intent detection
   - Natural language understanding
   - Flexible conversation flow

---

## LLM Calls & Decisions Summary

### Complete LLM Call Inventory

| # | Step | Purpose | Model | Input | Output | File |
|---|------|---------|-------|-------|--------|------|
| 1 | Greeting | Scope validation | GPT-4o-mini | "Hi" | "YES" | agents.py:197 |
| 2 | Greeting | Generate response | GPT-4o-mini | System prompt + "Hi" | "Hello! How can I assist you?" | agents.py:178 |
| 3 | Greeting | Route decision | GPT-4o-mini | Conversation context | "end" | router.py:164 |
| 4 | Describe issue | KB embedding | text-embedding-3-small | "issues with laptop" | 1536-dim vector | kb.py:102 |
| 5 | Describe issue | Generate response | GPT-4o-mini | System prompt + context | "Please describe..." | agents.py:178 |
| 6 | WiFi issue | KB embedding | text-embedding-3-small | "WiFi not working" | 1536-dim vector | kb.py:102 |
| 7 | WiFi issue | Solution response | GPT-4o-mini | KB solution + prompt | Troubleshooting steps | agents.py:161 |
| 8 | Confirmation | Parse action | GPT-4o-mini | "edit" | route="edit" | router.py:222 |
| 9 | Edit request | Extract changes | GPT-4o-mini + tools | "Change priority to High" | {priority: "High"} | agents.py:271 |

**Total LLM Calls**: 9  
**Total Cost**: ~$0.01 (with GPT-4o-mini)

---

## Key Decision Points

### 1. **Scope Validation** (Step 1)
```
IF first 1-2 messages:
    LLM checks: General/IT → YES, Other domain → NO
ELSE:
    Skip (already in conversation)
```

### 2. **KB vs Ticket** (Step 3)
```
IF KB confidence ≥ 0.4:
    Show solution
    DON'T offer ticket yet
ELSE IF KB confidence < 0.4:
    Ask for more details
```

### 3. **Ticket Offer Trigger** (Step 4)
```
IF (solution_failed AND conversation_length > 2)
   OR wants_ticket_explicit:
    Offer ticket creation
```

### 4. **Field Auto-fill** (Step 5-6)
```
Category: Use detected_category from KB search
Device: Match from conversation text
Priority: Ask user (can't infer reliably)
Description: Suggest from conversation context
```

### 5. **Edit Processing** (Step 8)
```
LLM with structured output (TicketSchema tool):
    Parse natural language edit request
    Extract changed fields
    Update ticket object
```

---

## Performance Characteristics

### Latency Breakdown (typical flow)

| Step | Operation | Time | Bottleneck |
|------|-----------|------|------------|
| 1 | Scope check | 0.5s | LLM call |
| 2 | KB search | 0.3s | Embedding generation |
| 3 | Solution generation | 0.7s | LLM call |
| 4 | Field collection | 0.1s | No LLM |
| 5 | Edit parsing | 0.6s | LLM with tools |
| 6 | Submit | 0.05s | File I/O |

**Total**: ~3-4 seconds for complete journey

### Optimization Opportunities

1. **Cache embeddings** for common queries
2. **Batch LLM calls** where possible
3. **Pre-load KB** at startup (already done)
4. **Use faster model** for simple tasks (already using gpt-4o-mini)

---

## Error Handling & Edge Cases

### 1. **LLM Failures**
```python
try:
    response = self.llm.invoke(...)
except Exception as e:
    # Fail-open: allow request to proceed
    return True
```

### 2. **KB Search Empty**
```python
if not results or results[0]["similarity"] < 0.3:
    # Fallback strategies
    # 1. Search without category filter
    # 2. Use conversation context
    # 3. Ask for more details
```

### 3. **Invalid User Input**
```python
# Priority selection
if user_input not in ["1", "2", "3", "4", "low", "medium", ...]:
    # Re-ask with clarification
    return {"messages": [AIMessage("Please enter 1-4...")]}
```

### 4. **Concurrent Edits**
```python
# State management prevents:
# - edit_mode flag ensures one edit at a time
# - awaiting_confirmation prevents multiple actions
```

---

## Presentation Tips

### Key Talking Points

1. **Hybrid Intelligence**
   - Rule-based for deterministic states
   - LLM-based for natural language understanding
   - Best of both worlds

2. **Context Preservation**
   - Detected category flows through entire journey
   - Conversation history enables smart pre-filling
   - State machine maintains conversation coherence

3. **User Experience**
   - Minimal questions (auto-fill when possible)
   - Natural conversation flow
   - Clear feedback at each step

4. **Scalability**
   - Add new categories: just update templates
   - Add new fields: modify schema
   - Add new KB docs: just add to JSON

### Demo Flow (5 minutes)

1. Show greeting + scope validation
2. Demonstrate KB search with high confidence
3. Show "didn't work" → ticket offer
4. Walk through field collection (note auto-fills)
5. Demonstrate edit with natural language
6. Show final ticket in JSON

### Code Deep Dive (10 minutes)

1. State machine architecture (main.py)
2. Agent delegation pattern (nodes.py → agents.py)
3. LLM structured outputs (edit parsing)
4. KB vector search (kb.py)
5. Routing logic (router.py)

---

## Conclusion

This architecture demonstrates:

✅ **Clean Separation of Concerns** (Nodes → Agents → Tools)  
✅ **Intelligent Context Management** (State flows through journey)  
✅ **Hybrid Decision Making** (Rules + LLM)  
✅ **User-Centric Design** (Minimal friction, smart defaults)  
✅ **Extensible Structure** (Easy to add features)

**Total Lines of Code**: ~2000  
**External Dependencies**: LangChain, LangGraph, OpenAI, ChromaDB  
**Deployment**: Single Python application with persistence

---

*Generated for presentation on December 22, 2025*
