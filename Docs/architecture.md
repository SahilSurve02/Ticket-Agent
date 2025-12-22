# Architecture Documentation

This document provides a detailed explanation of the internal architecture and code flow of the Ticket Agent system.

## High-Level Overview

The application is a sophisticated, multi-agent chatbot built using the `langgraph` library. The entire user interaction is modeled as a state machine, or a `StateGraph`, where each step in the conversation is a "node" and the transitions between these steps are governed by "edges."

The core of the system is a central `AgentState` dictionary (`src/state.py`) that acts as a shared memory or "data bus" for all components. This state is passed from node to node, allowing different parts of the system to access conversation history, the ticket being created, and various control flags.

The intelligence of the system is divided between two specialized agents defined in `src/agents.py`:

1.  **`ChatbotAgent` (Triage & First Response):** This is the user's first point of contact. It uses a Retrieval-Augmented Generation (RAG) pipeline, defined in `src/kb.py`, to search a knowledge base for solutions. If it cannot solve the issue, it initiates a handoff to the `TicketAgent`.
2.  **`TicketAgent` (Data Collection):** This agent takes over to create a formal support ticket. It is a methodical, form-filling agent that guides the user through the data collection process step-by-step, using predefined templates (`FORM_TEMPLATES` in `src/state.py`).

Control flow is managed by router functions, primarily defined in `main.py` and `src/router.py`, which inspect the `AgentState` to decide the next node in the graph.

## Detailed Code Flow from Entrypoint

The application is initiated from `main.py` (or `app.py` for the UI). Here is the step-by-step code execution flow:

1.  **Initialization (`main.py`):**
    *   The `main()` function is called.
    *   It initializes the knowledge base by calling `initialize_kb_with_check()` from `src/kb.py`. This function loads data from `data/kb.json` into the ChromaDB vector store if it hasn't been loaded already.

2.  **Graph Definition (`main.py`):**
    *   A `StateGraph` object is instantiated with the `AgentState` typed dictionary as its schema: `workflow = StateGraph(AgentState)`.
    *   **Nodes are added** to the graph using `workflow.add_node("node_name", node_function)`. Each `node_function` (e.g., `chatbot_node`, `ticket_collection_node`) is imported from `src/nodes.py`.
    *   **The entry point is set** using `workflow.set_entry_point("chatbot")`. This means every new conversation starts at the `chatbot_node`.

3.  **Edge and Routing Definition (`main.py`):**
    *   **Conditional Edges** are created using `workflow.add_conditional_edges()`. This is the core of the routing logic.
    *   For example, `workflow.add_conditional_edges("chatbot", route_chatbot_rules, ...)` means that after the "chatbot" node runs, the `route_chatbot_rules` function is called.
    *   The `route_chatbot_rules` function inspects the `AgentState` (e.g., checks `state['escalate_to_ticket']`) and returns the name of the next node to execute (e.g., `"ticket_collection"` or `"__end__"`).

4.  **Graph Compilation (`main.py`):**
    *   The graph definition is compiled into a runnable object: `app = workflow.compile()`.

5.  **Execution Loop (`main.py` -> `run_chat`):**
    *   The `run_chat` function contains the main `while` loop that interacts with the user.
    *   It takes user input and packages it into the `AgentState` format.
    *   It invokes the compiled graph with the current state: `app.invoke(inputs)`.
    *   `langgraph` then executes the appropriate node based on the current state, updates the state with the node's output, runs the corresponding router function to decide the next step, and so on.
    *   The final state is returned, and the latest message from the agent is printed to the console.

## The User's Journey: A Code-Centric View

This section maps the conceptual user journey to the specific functions and code execution paths.

1.  **Initial Interaction (Chatbot Node):**
    *   **Graph Node:** `chatbot`
    *   **Code:** The `chatbot_node` function in `src/nodes.py` is executed.
    *   **Action:** This node acts as a delegator. It gets the `ChatbotAgent` singleton (`get_chatbot_agent()`) and calls its main processing method: `agent.process(state)`.
    *   **`ChatbotAgent.process` (`src/agents.py`):** This method performs the core logic:
        *   Calls `self._check_it_scope()` to validate the user's query using an LLM call.
        *   Calls `detect_category()` and `get_best_solution()` from `src/kb.py` to perform a RAG search.
        *   Uses another LLM call to synthesize a response based on the search results.
        *   Updates the `AgentState` with its response and control flags (e.g., `awaiting_ticket_confirmation`).

2.  **Routing from Chatbot:**
    *   **Graph Edge:** Conditional edge sourced from the `chatbot` node.
    *   **Code:** The `route_chatbot_rules` function in `main.py` is executed.
    *   **Action:** It inspects the state returned by the `chatbot_node`.
        *   If `state.get("escalate_to_ticket")` is `True`, it returns the string `"ticket_collection"`, telling `langgraph` to go to that node next.
        *   Otherwise, it returns `"chatbot"`, looping back for more conversation.

3.  **Ticket Collection (Ticket Collection Node):**
    *   **Graph Node:** `ticket_collection`
    *   **Code:** The `ticket_collection_node` function in `src/nodes.py`.
    *   **Action:** This node delegates to the `TicketAgent`. It calls `get_ticket_agent().process_ticket_collection(state)`.
    *   **`TicketAgent.process_ticket_collection` (`src/agents.py`):** This is a complex method that:
        *   Checks if the user wants to edit the ticket. If so, it uses an LLM tool call to parse the edit request.
        *   Calls internal methods like `_auto_fill_fields` (which itself uses LLM calls for summary and extraction) and `_ask_next_field` to programmatically work through the required fields defined in `FORM_TEMPLATES`.
        *   Updates the `ticket` object within the `AgentState` after each piece of information is collected.

4.  **Routing During Ticket Collection:**
    *   **Graph Edge:** Conditional edge sourced from `ticket_collection`.
    *   **Code:** The `route_ticket_collection` function in `main.py`.
    *   **Action:** It checks if `state.get("ticket_collection_complete")` is `True`.
        *   If `True`, it returns `"ticket_preview"`.
        *   If `False`, it returns `"ticket_collection"`, looping back to ask the next question.

5.  **Ticket Preview (Ticket Preview Node):**
    *   **Graph Node:** `ticket_preview`
    *   **Code:** The `ticket_preview_node` function in `src/nodes.py`.
    *   **Action:** This is a simple node. It formats the `ticket` object from the `AgentState` into a human-readable summary and asks the user for confirmation. It does not call an agent.

6.  **Routing from Preview (Confirmation):**
    *   **Graph Edge:** Conditional edge sourced from `ticket_preview`.
    *   **Code:** The `route_preview` function in `main.py`.
    *   **Action:** It checks the `confirmation_action` flag in the state, which is set based on the user's response ("yes", "edit", "cancel"). It returns `"submit_ticket"`, `"ticket_collection"` (for edits), or `"__end__"`.

7.  **Ticket Submission (Submit Ticket Node):**
    *   **Graph Node:** `submit_ticket`
    *   **Code:** The `submit_ticket_node` function in `src/nodes.py`.
    *   **Action:** It takes the final `TicketSchema` object, assigns a `ticket_id` and `timestamp`, and appends the ticket as a JSON object to `data/tickets.json`.

8.  **Final Confirmation (Ticket Confirmation Node):**
    *   **Graph Node:** `ticket_confirmation`
    *   **Code:** The `ticket_confirmation_node` function in `src/nodes.py`.
    *   **Action:** Creates the final confirmation message with the new ticket ID.

## Component Breakdown

### Entrypoints: `main.py` and `app.py`
*   **Role:** Define and run the `langgraph` state machine.
*   **Key Functions:**
    *   `main()` / `build_workflow()`: Where the `StateGraph` is instantiated, nodes are added, and edges are defined. This is the master blueprint of the application flow.
    *   `run_chat()`: The main loop that gets user input, calls `app.invoke(inputs)`, and prints the output.
    *   **Router Functions** (`route_chatbot_rules`, `route_ticket_collection`, `route_preview`): The explicit control-flow logic that connects the graph nodes.

### State: `src/state.py`
*   **Role:** The single source of truth for the application's state.
*   **Key Components:**
    *   `AgentState`: A `TypedDict` that defines the schema for the graph's memory. Every node receives and returns this object (or a subset of it).
    *   `TicketSchema`: A `Pydantic` model ensuring the ticket data is structured and validated.
    *   `FORM_TEMPLATES`: A configuration dictionary that makes the ticket collection process dynamic and extensible without changing agent code.

### Nodes: `src/nodes.py`
*   **Role:** The executable units of the graph. They are the "verbs" of the application flow.
*   **Pattern:** Most nodes are simple delegators. They receive the `state`, call the appropriate agent's method, and return the `state` changes provided by the agent.
    *   `chatbot_node(state)` -> `get_chatbot_agent().process(state)`
    *   `ticket_collection_node(state)` -> `get_ticket_agent().process_ticket_collection(state)`
*   Some nodes, like `ticket_preview_node` and `submit_ticket_node`, contain their own simple logic and do not call an agent.

### Agents: `src/agents.py`
*   **Role:** The "brains" of the operation, containing the core LLM logic.
*   **Key Methods:**
    *   `ChatbotAgent.process()`: Orchestrates scope checking, KB search, and conversational response generation.
    *   `ChatbotAgent._extract_ticket_fields()`: Uses a structured LLM call to perform entity extraction from natural language.
    *   `TicketAgent.process_ticket_collection()`: Manages the step-by-step form filling logic, including handling user edits via LLM-powered intent recognition.
    *   `TicketAgent._auto_fill_fields()` / `_generate_conversation_summary()`: Use LLM calls to intelligently populate ticket fields like summaries and descriptions, creating a high-quality data record.

### Router: `src/router.py`
*   **Role:** Provides an optional, more advanced LLM-based routing mechanism.
*   **Functionality:** While `main.py` uses simple rule-based routers, `src/router.py` defines a `HybridRouter`. This demonstrates a more sophisticated pattern where an LLM can be used to decide the next step if simple rule flags aren't sufficient, allowing for more fluid, intent-driven conversations.

### Knowledge Base: `src/kb.py`
*   **Role:** Implements the entire Retrieval-Augmented Generation (RAG) pipeline.
*   **Key Functions:**
    *   `initialize_kb_with_check()`: A one-time setup function to embed `data/kb.json` into the `ChromaDB` vector store.
    *   `detect_category()`: Uses an LLM call to classify the user's query into a predefined category, allowing for a more focused search.
    *   `get_best_solution()`: The core RAG function. It takes the user's query, performs a similarity search on the vector database, and returns the most relevant documents.
