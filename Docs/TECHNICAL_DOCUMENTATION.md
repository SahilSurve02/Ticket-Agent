# Ticket Agent - Non-UI Technical Documentation

This document provides a detailed explanation of the non-ui components of the Ticket Agent project.

## Table of Contents
1.  [High-Level Overview](#high-level-overview)
2.  [Project Structure](#project-structure)
3.  [Core Components](#core-components)
    - [State Management (`src/state.py`)](#state-management-srcstatepy)
    - [Knowledge Base (`src/kb.py`)](#knowledge-base-srckbpy)
    - [The Agents (`src/agents.py`)](#the-agents-srcagentspy)
    - [Graph Nodes (`src/nodes.py`)](#graph-nodes-srcnodespy)
    - [Main Application Logic (`main.py`)](#main-application-logic-mainpy)
4.  [Data Files](#data-files)
5.  [Execution Flow](#execution-flow)
6.  [Key Dependencies](#key-dependencies)

## 1. High-Level Overview

The Ticket Agent is a sophisticated, multi-agent system designed to automate IT support. It leverages large language models (LLMs) and a knowledge base to provide initial troubleshooting and, if necessary, guide a user through the process of creating a detailed IT support ticket.

The system is built using the **LangGraph** framework, which allows for the creation of cyclical, stateful, multi-agent workflows. The core of the application is a state machine where different nodes (representing different stages of the conversation) are executed based on the current state.

The two primary agents are:
-   **Chatbot Agent**: The user's first point of contact. It uses a knowledge base to answer user questions and provide solutions.
-   **Ticket Agent**: This agent takes over when the Chatbot Agent determines that a support ticket is necessary. It guides the user through a structured process to collect all the required information for a ticket.

The entire process is managed by a state graph that routes the conversation between the user, the Chatbot Agent, and the Ticket Agent, ensuring a smooth and logical user experience.

## 2. Project Structure

The repository is organized into several key files and directories that separate concerns such as application entry point, core logic, data, and documentation.

```
d:\Ticket-Agent\
├─── main.py                # Main entry point for the console application and graph definition
├─── requirements.txt       # Python dependencies
├─── TECHNICAL_DOCUMENTATION.md # This file
├─── data\
│    ├─── kb.json           # Source of truth for the knowledge base articles
│    └─── tickets.json      # Where submitted tickets are stored
├─── chroma_db\              # Directory for the ChromaDB vectorized knowledge base
│    └─── ...
├─── src\
│    ├─── agents.py         # Defines the Chatbot and Ticket agents
│    ├─── kb.py             # Handles knowledge base creation, loading, and searching
│    ├─── nodes.py          # Contains the functions that make up the nodes in the LangGraph
│    └─── state.py          # Defines the state schema for the application
└─── ...
```

## 3. Core Components

This section provides a deep dive into the main Python modules that power the application.

### State Management (`src/state.py`)

This file is central to the application's architecture. It defines the data structures that hold the application's state throughout the conversation.

#### `TicketSchema`

A Pydantic `BaseModel` that serves as the schema for an IT support ticket. It defines all the possible fields a ticket can have, including:
-   **Auto-generated fields**: `ticket_id`, `created_at`.
-   **User information**: `user_id`, `user_name`, `email`, etc. (In this version, this is simulated, but in a real application, it would come from a user session).
-   **Issue classification**: `category`.
-   **Core ticket fields**: `issue_summary`, `device_id`, `priority`, `description`. These are the main pieces of information collected from the user.
-   **`extra_fields`**: A dictionary to hold category-specific information (e.g., `connection_type` for a "Network" issue).

Using a Pydantic model ensures that the ticket data is always well-structured and validated.

#### `AgentState`

This is a `TypedDict` that represents the entire state of the LangGraph workflow at any given moment. The state is passed between nodes, and each node can read from or write to it. Key fields include:
-   `messages`: A list of all messages in the conversation history. LangGraph uses this to maintain context.
-   `ticket`: An instance of `TicketSchema`, holding the information for the ticket currently being created.
-   `user_info` & `user_devices`: Simulated user data.
-   `detected_category`: The issue category as detected by the `ChatbotAgent`.
-   **Workflow and Form Tracking**: Various flags and fields like `awaiting_confirmation`, `last_question`, and `current_extra_field_index` that control the flow of the conversation, especially during the ticket creation process.
-   `current_agent`: A field to track which agent is currently active ("chatbot" or "ticket").

#### Form Templates

The `FORM_TEMPLATES` dictionary defines the unique fields required for each ticket category. This allows the `TicketAgent` to dynamically ask for the correct information based on the type of issue. For example, a "Hardware" issue will prompt for the `component` and `physical_damage`, while a "Software" issue will ask for the `application_name`.
### Knowledge Base (`src/kb.py`)

This module manages the knowledge base, from its creation to searching for solutions. It uses a combination of a JSON file for raw data and a ChromaDB vector store for efficient searching.

#### `KnowledgeBase` Class
-   This class encapsulates the logic for the knowledge base.
-   Upon initialization, it sets up a `Chroma` vector store using `text-embedding-3-small` from OpenAI to generate embeddings.
-   The vector store is configured to persist its data to the `chroma_db` directory.

#### `initialize_kb_with_check` Function
-   This is the main entry point for creating the KB.
-   It first initializes the `KnowledgeBase` object.
-   It then checks if the ChromaDB collection has any documents. If it's empty, it calls `load_knowledge_base` to populate it from `data/kb.json`. This ensures that the KB is loaded only once when the application starts.

#### `load_knowledge_base` Function
-   Reads the `data/kb.json` file.
-   For each article in the JSON file, it constructs a rich text document containing the title, category, symptoms, and solution.
-   It uses a `RecursiveCharacterTextSplitter` to break down large articles into smaller chunks.
-   Finally, it adds these chunks (as vector embeddings) to the ChromaDB vector store along with metadata like title and category.

#### `search_knowledge` and `get_best_solution`
-   `search_knowledge` performs a semantic similarity search against the ChromaDB vector store. It can filter by category and a minimum similarity score to ensure the relevance of results.
-   `get_best_solution` is a higher-level function that uses `search_knowledge` to find the most relevant solution. It employs a multi-strategy approach:
    1.  First, it searches with the user's query and a detected category.
    2.  If the results aren't good enough, it falls back to searching without a category filter.
    3.  As a final attempt, it enhances the query with the recent conversation history to provide more context.
-   Based on the similarity score of the best result, it returns a confidence level ("high", "medium", or "low").

### The Agents (`src/agents.py`)

This module contains the "brains" of the operation. It defines the classes for the `ChatbotAgent` and `TicketAgent`, which handle the core logic of the conversation.

#### `ChatbotAgent`
The `ChatbotAgent` is the user's first point of contact. Its primary responsibilities are:
-   **Troubleshooting**: It takes the user's message, searches the knowledge base using `get_best_solution`, and provides potential solutions.
-   **Detecting Escalation**: It analyzes the user's message for keywords or phrases (like "didn't work" or "create a ticket") that indicate the user needs more help.
-   **Handoff Confirmation**: If it determines that a ticket is needed, it doesn't immediately hand over to the `TicketAgent`. Instead, it first asks the user for confirmation (e.g., "Would you like me to create a support ticket?"). This is a crucial step for a good user experience.
-   **Agent Handoff**: Once the user confirms, it adds a special `HANDOFF_TO_TICKET_AGENT` message to the state. The routing logic in `main.py` uses this signal to switch to the `ticket_collection` node.

#### `TicketAgent`
The `TicketAgent` takes over once the handoff is initiated. Its sole focus is to collect the necessary information to file a complete ticket.
-   **Step-by-Step Information Gathering**: The agent guides the user through the ticket creation process one question at a time. It uses the `last_question` field in the `AgentState` to keep track of what it needs to ask next.
-   **Auto-filling Fields (`_auto_fill_fields`)**: This is a key feature. Before asking a question, the agent attempts to automatically fill in ticket fields by analyzing the conversation history. It uses an LLM call to:
    -   Extract a concise `issue_summary` from the user's initial problem description.
    -   Detect the `device_id` and `priority` based on keywords.
    -   This minimizes the number of questions the user has to answer.
-   **Dynamic Questions**: It uses the `FORM_TEMPLATES` from `state.py` to ask for category-specific information.
-   **Handling Edits**: If the user wants to edit the ticket after seeing the preview, the `TicketAgent` processes the user's request (e.g., "change the priority to high") using an LLM call with tool-enforced schema to identify which fields to update.
-   **Completion Signal**: Once all the required fields are filled, it sets the `ticket_collection_complete` flag in the state, signaling the router to move to the `ticket_preview` node.

### Graph Nodes (`src/nodes.py`)

This file defines the functions that act as nodes in the LangGraph workflow. Each node is a callable that receives the current `AgentState` and returns a dictionary to update the state.

-   **`chatbot_node`**: This node is the main entry point. It delegates its logic to the `ChatbotAgent`.
-   **`ticket_collection_node`**: This node delegates its logic to the `TicketAgent` to handle the step-by-step process of filling out the ticket.
-   **`ticket_preview_node`**: This node is responsible for displaying the collected ticket information to the user for review. It formats the ticket data into a readable preview and asks the user to "submit", "edit", or "cancel".
-   **`ticket_confirmation_node`**: This node processes the user's response to the preview. It updates the state based on whether the user chose to submit, edit, or cancel.
-   **`submit_ticket_node`**: This is the final node in the ticket creation process. It generates a unique `ticket_id`, adds a timestamp, saves the complete ticket to `data/tickets.json`, and informs the user of the successful submission.

### Main Application Logic (`main.py`)

This file ties everything together. It defines the LangGraph `StateGraph` and the routing logic that controls the flow of the conversation.

#### Graph Definition
-   It initializes a `StateGraph` with the `AgentState`.
-   It adds all the functions from `src/nodes.py` as nodes to the graph.
-   The entry point is set to the `chatbot` node.

#### Routing Logic
This is the most critical part of `main.py`. It consists of several conditional routing functions that are executed after a node completes its work. These functions inspect the `AgentState` to decide which node to move to next.
-   **`route_chatbot`**: Decides where to go from the chatbot. If the handoff signal is present, it moves to `ticket_collection`. If the user is being asked for confirmation, it stays in the `chatbot` node (`END` for the current step).
-   **`route_ticket_collection`**: After the `TicketAgent` has run, this router checks if the ticket is complete. If yes, it moves to `ticket_preview`; otherwise, it waits for the next user input.
-   **`route_confirmation`**: Based on the user's choice ("submit", "edit", or "cancel"), it routes to the appropriate node (`submit_ticket`, back to `ticket_collection` via `chatbot` for user input, or ends the ticket process).

#### `run_chat()`
-   This function sets up the application and runs the main command-line interface loop.
-   It initializes the knowledge base by calling `initialize_kb_with_check`.
-   It compiles the graph with a `MemorySaver` to make the conversation stateful.
-   It then enters a `while` loop, taking user input, passing it to the compiled graph, and printing the bot's responses.

## 4. Data Files

-   **`data/kb.json`**: This JSON file is the master source for the knowledge base. It contains a list of articles, where each article is a JSON object with fields like `title`, `category`, `symptoms`, and `solution`. Its human-readable format makes it easy to manage.
-   **`data/tickets.json`**: This file is the destination for all successfully submitted tickets. Each time a ticket is created, it's appended to the list in this file, providing a simple database of all created tickets.

## 5. Execution Flow

Here is a step-by-step walkthrough of a common user interaction:

1.  **Initialization**: The user runs `main.py`. The `run_chat()` function initializes the knowledge base (loading from `kb.json` into ChromaDB if empty) and compiles the LangGraph.
2.  **User Input**: The user describes their problem (e.g., "my wifi is not working").
3.  **Chatbot Node**: The input is sent to the `chatbot_node`. The `ChatbotAgent` searches the KB for solutions related to "wifi".
4.  **Provide Solution**: The agent finds a relevant article and presents the solution to the user.
5.  **User Feedback**: The user tries the solution and reports that it "didn't work".
6.  **Handoff Detection**: The `chatbot_node` runs again. The `ChatbotAgent` detects the negative feedback and asks the user if they want to create a ticket.
7.  **User Confirmation**: The user replies "yes".
8.  **Routing to Ticket Agent**: The `ChatbotAgent` adds the handoff signal to the state. The `route_chatbot` function sees this signal and routes the workflow to the `ticket_collection_node`.
9.  **Ticket Collection**: The `ticket_collection_node` is now active. The `TicketAgent` takes over and begins asking the user for information (category, device, priority, etc.), attempting to auto-fill fields where possible.
10. **Looping**: For each piece of information the user provides, the `ticket_collection_node` runs, processes the answer, and asks the next question. The `route_ticket_collection` router keeps the process in this loop (`END`) until all data is gathered.
11. **Ticket Preview**: Once the `TicketAgent` determines the ticket is complete, the `route_ticket_collection` router moves to the `ticket_preview_node`. The user is shown a summary of the ticket.
12. **Final Confirmation**: The user types "submit". The `ticket_confirmation_node` processes this, and the `route_confirmation` function directs the flow to `submit_ticket_node`.
13. **Submission**: The `submit_ticket_node` generates the final ticket, saves it to `tickets.json`, and displays a success message to the user. The workflow is now complete for this interaction.

## 6. Key Dependencies

-   **`langchain` / `langgraph`**: The core framework for building the agentic workflow and state machine.
-   **`langchain-openai`**: Provides the integration with OpenAI's models for LLM functionality and embeddings.
-   **`chromadb` / `langchain-chroma`**: The vector database used for the knowledge base and its LangChain integration.
-   **`pydantic`**: Used for data validation and defining the `TicketSchema`. This ensures data integrity throughout the application.
-   **`python-dotenv`**: Used to manage environment variables, such as the OpenAI API key.