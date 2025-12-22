# Architecture Documentation

This document provides a detailed explanation of the internal architecture of the Ticket Agent system.

## High-Level Overview

The application is a sophisticated, multi-agent chatbot built using the `langgraph` library. The entire user interaction is modeled as a state machine, or a `StateGraph`, where each step in the conversation is a "node" and the transitions between these steps are governed by "edges."

The core of the system is a central `AgentState` dictionary that acts as a shared memory or "data bus" for all components. This state is passed from node to node, allowing different parts of the system to access conversation history, the ticket being created, and various control flags.

The intelligence of the system is divided between two specialized agents:

1.  **ChatbotAgent (Triage & First Response):** This is the user's first point of contact. It uses a Retrieval-Augmented Generation (RAG) pipeline to search a knowledge base (`data/kb.json`) for solutions to the user's problem. If it cannot find a solution, it initiates a handoff to the TicketAgent.
2.  **TicketAgent (Data Collection):** This agent takes over to create a formal support ticket. It is a methodical, form-filling agent that guides the user through the data collection process step-by-step, using predefined templates for different ticket categories (e.g., "Software," "Hardware").

Control flow (the movement between nodes) is managed by routers, which can be simple rule-based functions or a more advanced `HybridRouter` that uses a Large Language Model (LLM) to understand the user's intent.

## The User's Journey: Filing a Ticket

The following steps outline a typical user journey from starting a conversation to successfully filing a ticket.

1.  **Initial Interaction (Chatbot Node):**
    *   The user sends their initial message (e.g., "My printer is not working").
    *   The `chatbot_node` is activated. It delegates the work to the `ChatbotAgent`.
    *   The `ChatbotAgent` searches the knowledge base for relevant solutions.
    *   If a solution is found, it's presented to the user. The user can either confirm that the issue is resolved or state that they still need help.
    *   If no solution is found, or if the user indicates they still need help, the agent decides a ticket is necessary and initiates a "handoff."

2.  **Routing from Chatbot:**
    *   After the chatbot node, a router (`route_chatbot_rules`) inspects the `AgentState`.
    *   If the state indicates a handoff is required (`handoff_to_ticket_agent` is `True`), the router directs the flow to the `ticket_collection_node`.
    *   Otherwise, the flow loops back to the `chatbot_node` for continued conversation.

3.  **Ticket Collection (Ticket Collection Node):**
    *   The `ticket_collection_node` is activated, which delegates to the `TicketAgent`.
    *   The `TicketAgent` first identifies the ticket category (e.g., "Hardware") and then uses a predefined template (`FORM_TEMPLATES` from `src/state.py`) to determine what information it needs to collect (e.g., "asset_id", "priority").
    *   It asks the user for one piece of information at a time (e.g., "What is the asset ID of the printer?").
    *   The user's responses are collected and stored in the `TicketSchema` object within the `AgentState`.

4.  **Routing During Ticket Collection:**
    *   After each user response in the ticket collection phase, the `route_ticket_collection` router checks if all required information for the current template has been gathered.
    *   If more information is needed, it routes back to the `ticket_collection_node`.
    *   Once all fields are filled, it sets `ticket_collection_complete` to `True` and routes the flow to the `ticket_preview_node`.

5.  **Ticket Preview (Ticket Preview Node):**
    *   The `ticket_preview_node` is activated.
    *   It displays a summary of the collected ticket information to the user and asks for confirmation ("Does this look correct?").

6.  **Routing from Preview (Confirmation):**
    *   The `route_preview` router analyzes the user's response.
    *   **If the user confirms ("yes"):** It routes to the `submit_ticket_node`.
    *   **If the user wants to make a change ("no", "I need to change the priority"):** It routes back to the `ticket_collection_node`. The `TicketAgent` is smart enough to handle edit requests (e.g., "change the priority to High") and will update the specific field before asking for confirmation again.
    *   **If the user cancels:** It routes to an `end_node`.

7.  **Ticket Submission (Submit Ticket Node):**
    *   The `submit_ticket_node` is activated.
    *   It takes the final `TicketSchema` object from the state.
    *   It assigns a unique `ticket_id` and a `timestamp`.
    *   It saves the complete ticket as a JSON object to the `data/tickets.json` file.
    *   It then moves to the `ticket_confirmation_node`.

8.  **Final Confirmation (Ticket Confirmation Node):**
    *   The `ticket_confirmation_node` provides the user with their final ticket ID and a confirmation message. The process is now complete.

## Component Breakdown

### Entrypoints: `main.py` and `app.py`

*   **Role:** These files are the entry points for the command-line interface and the Streamlit web UI, respectively.
*   **Functionality:** Both files are responsible for:
    1.  Initializing the `StateGraph`.
    2.  Adding all the nodes (`chatbot`, `ticket_collection`, etc.).
    3.  Defining the conditional edges (the routing logic) that connect the nodes.
    4.  Compiling the graph into a runnable `workflow` object.
    5.  Running the main application loop.
*   **Architectural Note:** The graph definition is unfortunately duplicated across both files. A key improvement would be to centralize this graph-building logic into a single function that both `main.py` and `app.py` can import and use.

### State: `src/state.py`

*   **Role:** This is the data-centric heart of the application. It defines the structure of the shared memory (`AgentState`) that is passed between all nodes in the graph.
*   **Key Components:**
    *   `TicketSchema`: A `Pydantic` model that defines the structure of a support ticket (e.g., `title`, `category`, `priority`, `description`). This ensures data consistency.
    *   `AgentState`: A `TypedDict` that represents the entire state of the application at any given moment. It includes:
        *   `messages`: The history of the conversation.
        *   `ticket`: The `TicketSchema` object being built.
        *   `form_to_fill`: The current template being used by the `TicketAgent`.
        *   Control flags like `handoff_to_ticket_agent` and `ticket_collection_complete`.
    *   `FORM_TEMPLATES`: A dictionary that maps ticket categories to the list of fields that need to be collected. This makes the system easily extensible to new ticket types.

### Nodes: `src/nodes.py`

*   **Role:** This file contains the implementation for every "step" or "state" in our workflow graph.
*   **Functionality:** Each function in this file corresponds to a node in the graph. The primary responsibility of most nodes is to call the appropriate agent (`ChatbotAgent` or `TicketAgent`) to perform the actual work and then update the `AgentState` with the results.
    *   `chatbot_node`: Calls the `ChatbotAgent`.
    *   `ticket_collection_node`: Calls the `TicketAgent`.
    *   `ticket_preview_node`: Formats the ticket data for user review.
    *   `submit_ticket_node`: Saves the ticket to the filesystem.
    *   `ticket_confirmation_node`: Generates the final confirmation message.

### Agents: `src/agents.py`

*   **Role:** This file contains the core intelligence and decision-making logic of the system.
*   **Key Components:**
    *   `ChatbotAgent`:
        *   **Purpose:** Triage and initial support.
        *   **How it works:** It uses `langchain` tools, including the `KnowledgeBase` (`src/kb.py`), to search for solutions. It is prompted to be helpful and conversational, but also to recognize when it cannot solve a problem and must escalate to creating a ticket.
    *   `TicketAgent`:
        *   **Purpose:** Structured data collection.
        *   **How it works:** This agent is prompted to be more methodical. It receives the current conversation and the `form_to_fill` template. Its job is to either ask the next unanswered question from the template or, if the user is making an edit, to parse that edit request and update the ticket accordingly.

### Router: `src/router.py`

*   **Role:** This file defines the logic for controlling the flow of the conversation. It implements the "conditional edges" of our `StateGraph`.
*   **Functionality:**
    *   **Rule-Based Routers (e.g., `route_chatbot_rules`):** These are simple Python functions that use `if/else` statements to check for boolean flags in the `AgentState` (e.g., `if state['handoff_to_ticket_agent']:`). They are fast and deterministic.
    *   **LLM-Based Routers (`HybridRouter`, `LLMRouter`):** This provides a more advanced and flexible routing mechanism. The `HybridRouter` first checks a set of deterministic rules. If no rule matches, it falls back to the `LLMRouter`, which sends the conversation history to an LLM. The LLM is prompted to analyze the user's intent and decide which node the conversation should move to next. This allows for more natural conversation, as the user doesn't have to use specific keywords.

### Knowledge Base: `src/kb.py`

*   **Role:** Implements the Retrieval-Augmented Generation (RAG) functionality.
*   **Functionality:**
    *   **`KnowledgeBase` class:** Manages the interaction with a `ChromaDB` vector store.
    *   **`initialize_kb_with_check`:** Checks if the knowledge base (`data/kb.json`) has already been processed and stored in `ChromaDB`. If not, it embeds the JSON data using `OpenAIEmbeddings` and saves it. This prevents re-processing the data on every run.
    *   **`get_best_solution`:** The core retrieval function. It takes a user's query, embeds it, and performs a similarity search against the vector database to find the most relevant solutions from the knowledge base.