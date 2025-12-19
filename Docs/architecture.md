# Ticket-Agent Architecture Overview

This document provides a detailed overview of the `Ticket-Agent` repository, its architecture, and recommendations for improvement.

## What does this repository do?

This repository contains a sophisticated, multi-agent IT Support Chatbot built with LangGraph. The primary purpose of this application is to automate the initial stages of IT support. It functions as a "first line of defense" that can either solve user problems by providing relevant information from a knowledge base or, if a solution isn't found, guide the user through creating a detailed and well-structured support ticket.

The system is designed to be run from the command line and simulates a conversation with an IT support agent.

## Architecture

The system is built as a stateful graph using the LangGraph library. This architecture allows for a robust and predictable flow of conversation, where different "nodes" in the graph are responsible for specific tasks. The core components of the architecture are:

1.  **Stateful Graph (`main.py`):** The entire application is orchestrated by a `StateGraph` defined in `main.py`. This graph defines the possible states and transitions in the conversation. The state is managed by the `AgentState` TypedDict (`src/state.py`), which acts as the shared memory for the entire system.

2.  **Nodes (`src/nodes.py`):** Each node in the graph represents a step in the process. The key nodes are:
    *   `chatbot_node`: The entry point for user interaction.
    *   `ticket_collection_node`: Gathers information for a support ticket.
    *   `ticket_preview_node`: Shows the user a preview of the ticket before submission.
    *   `submit_ticket_node`: The final step, which (currently) prints the ticket details.

3.  **Conditional Routing (`main.py`):** The graph uses conditional edges (`route_chatbot`, `route_ticket_collection`) to make decisions. For example, after the `chatbot_node` runs, `route_chatbot` checks if a solution was found. If so, the conversation can end. If not, it routes the conversation to the `ticket_collection_node`.

4.  **Retrieval-Augmented Generation (RAG) (`src/kb.py`, `src/agents.py`):** The `ChatbotAgent` uses a RAG pipeline to answer user queries.
    *   **Knowledge Base:** The knowledge base is stored in `data/kb.json`.
    *   **Vector Store:** On startup, the knowledge base is loaded into a ChromaDB vector store (`src/kb.py`).
    *   **Search:** When a user sends a message, the system searches the vector store for relevant solutions (`search_knowledge` in `src/kb.py`).

## Is this a single-agent or multi-agent system?

This is a **multi-agent system**. The agents have clearly separated roles and responsibilities, which makes the system modular and easier to maintain.

## If multi-agent, how are they working?

The system has two primary agents defined in `src/agents.py`:

1.  **`ChatbotAgent` (The "Triage Specialist"):**
    *   **Responsibility:** Handles the initial user interaction, understands the user's problem, and tries to find a solution.
    *   **Function:** It takes the user's query and uses the `search_knowledge` function to query the RAG pipeline. It then uses a language model to determine if any of the retrieved solutions are relevant. It's also responsible for the "handoff" detection, deciding when it's time to stop searching for solutions and start creating a ticket.

2.  **`TicketAgent` (The "Administrator"):**
    *   **Responsibility:** Manages the structured task of creating a support ticket.
    *   **Function:** Once the system transitions to ticket creation, the `TicketAgent` takes over. It uses predefined `FORM_TEMPLATES` (`src/state.py`) based on the detected category of the problem (e.g., "General IT," "Software," "Hardware"). It then interacts with the user in a form-like manner to collect all the necessary information (e.g., "What is the asset ID of your device?").

The agents do not act autonomously in parallel. Instead, they are called by the LangGraph framework in a predefined, state-driven flow. This ensures a predictable and robust user experience. The `StateGraph` in `main.py` explicitly defines when each agent (via its corresponding node) is activated.

## Recommendations for Improvement

1.  **Implement Real Ticket Submission:** The `submit_ticket_node` currently only prints the ticket data to the console. This should be integrated with a real ticketing system like **Jira, ServiceNow, or Zendesk** via an API call.

2.  **Dynamic KB Management:** The knowledge base is a static `kb.json` file. This is not ideal for a real-world scenario. A significant improvement would be to create a simple web interface or a set of scripts for IT staff to add, remove, and update knowledge base articles without needing to modify code or restart the application.

3.  **Add a Web Interface:** The project includes FastAPI in its requirements, but it's only run from the command line. Building out the API endpoints and creating a proper web-based chat interface would make the application much more user-friendly.

4.  **Comprehensive Testing:** The project lacks any form of automated testing. Adding **unit tests** for the agent logic (`src/agents.py`) and **integration tests** for the LangGraph workflow (`main.py`) is crucial for ensuring the application is stable and maintainable in the long term.

5.  **Configuration Management:** Hardcoded values like model names (`gpt-4o-mini`) and prompts should be externalized into a configuration file (e.g., `config.yaml` or `.env`). This makes the application more flexible and easier to configure for different environments.

6.  **Establish a Feedback Loop:** The system could be enhanced by asking the user if the provided solution from the knowledge base was helpful. This feedback could be logged and used to create a feedback loop to automatically improve the ranking of solutions or flag articles that are not useful for review.

7.  **More Sophisticated State Management:** For more complex scenarios, the `AgentState` could be expanded to track more context, such as user sentiment or a more detailed history of attempted solutions.
