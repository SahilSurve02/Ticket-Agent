# Analysis and Improvement Plan

This document provides an analysis of the "Ticket-Agent" application's LLM usage and cost, along with a set of actionable recommendations to elevate the project to an industry-standard asset.

## Part 1: LLM Call & Cost Analysis

The system leverages two OpenAI models:
-   **Chat/Reasoning:** `gpt-4o-mini`
-   **Embeddings:** `text-embedding-3-small`

### Cost Breakdown

| Model | Usage | Price |
| :--- | :--- | :--- |
| `gpt-4o-mini` | Input Tokens | **$0.15 / 1M tokens** |
| | Output Tokens | **$0.60 / 1M tokens** |
| `text-embedding-3-small` | Input Tokens | **$0.02 / 1M tokens** |

*Note: Prices are subject to change. This analysis is based on pricing as of late 2025.*

### Call Frequency per Request

The number of LLM calls depends on the user's interaction with the chatbot.

1.  **Knowledge Base Embedding (One-Time Cost):**
    *   The `text-embedding-3-small` model is used once to create vector embeddings for the `data/kb.json` file. This is not a recurring cost per request but is a setup cost. Given the small size of the KB and the low price of the embedding model, this cost is negligible.

2.  **Chat Interaction (Per-Turn Cost):**
    *   Every message the user sends to the `ChatbotAgent` triggers one call to `gpt-4o-mini`. If the user and bot have a 4-turn conversation before the issue is resolved or handed off, that equates to **4 LLM calls**.

3.  **Ticket Creation (Fixed Cost per Ticket):**
    *   When the conversation is handed off to the `TicketAgent`, a fixed sequence of **2 additional `gpt-4o-mini` calls** is triggered:
        1.  **Generate Ticket Summary:** The agent generates a one-line summary of the issue.
        2.  **Generate Ticket Description:** The agent generates a detailed, structured description for the ticket body.

### Example Scenarios:

*   **Scenario A: Issue resolved by chatbot**
    *   User asks a question.
    *   Chatbot answers it successfully after a 3-turn conversation.
    *   **Total Cost:** 3 `gpt-4o-mini` calls.

*   **Scenario B: Ticket is created**
    *   User describes an issue.
    *   Chatbot is unable to resolve it after a 2-turn conversation.
    *   The workflow hands off to the ticket creation agent.
    *   The ticket agent runs its two calls to generate the ticket details.
    *   **Total Cost:** 2 (chat) + 2 (ticket) = **4 `gpt-4o-mini` calls**.

**Conclusion:** The primary recurring cost is the `gpt-4o-mini` model. A typical ticket creation flow costs at least 3-4 calls, plus any preceding conversation turns. While `gpt-4o-mini` is cost-effective, high-volume usage will still incur notable costs. Caching common KB queries could be a future cost-saving measure.

---

## Part 2: Path to "Industry Level"

The current implementation is a strong proof-of-concept. To make it a robust, scalable, and maintainable "industry level usable asset," the following improvements are recommended.

### 1. Refactor Duplicated Workflow Logic
*   **Problem:** The core LangGraph workflow, state, and routing logic is duplicated in `main.py` (CLI) and `app.py` (Streamlit UI). This means any change to the workflow must be made in two places, increasing the risk of bugs and inconsistencies.
*   **Recommendation:**
    *   Create a new file, `src/workflow.py`.
    *   Move the `StateGraph` definition, node setup, and compilation logic into a reusable function within this new file (e.g., `create_workflow()`).
    *   Refactor both `main.py` and `app.py` to import and call this function, removing the duplicated code. This ensures a single source of truth for the application's core logic.

### 2. Externalize Configuration
*   **Problem:** The LLM model name (`gpt-4o-mini`) is hardcoded directly in `src/agents.py`. This makes it difficult to switch models, test with different versions, or update the model without changing the code.
*   **Recommendation:**
    *   Use a dedicated configuration file (e.g., `config.py`) or environment variables (`.env` file) to manage all settings.
    *   Store the model name, temperature, API keys, and other configurable parameters there.
    *   Load this configuration at application startup. This allows for easy updates and environment-specific setups (e.g., using a cheaper model for development/testing).

### 3. Integrate with a Real Ticketing System
*   **Problem:** Tickets are currently saved to a local `tickets.json` file. This is not scalable, provides no visibility to a support team, and lacks features like status tracking, assignments, and commenting.
*   **Recommendation:**
    *   Replace the `submit_ticket_node`'s file-writing logic with an API client that connects to a real ticketing system (e.g., Jira, ServiceNow, Zendesk).
    *   Create a dedicated module (e.g., `src/ticketing_client.py`) to handle the API interactions.
    *   Store API credentials securely using a secrets management system, not in the configuration file.

### 4. Implement a Comprehensive Test Suite
*   **Problem:** There are no automated tests for the agents, workflow logic, or utility functions. This makes it risky to refactor code or add new features, as regressions may go unnoticed.
*   **Recommendation:**
    *   Introduce a testing framework like `pytest`.
    *   Write unit tests for individual functions (e.g., agent prompt generation, KB loading).
    *   Write integration tests for the entire workflow. Mock the LLM calls (`ChatOpenAI`) to test the application's logic in isolation, ensuring predictable outcomes without incurring real API costs. Test the conditional routing (`route_chatbot`) to verify that handoffs occur correctly.

### 5. Create a KB Management System
*   **Problem:** The knowledge base (`kb.json`) is a static file that can only be updated by a developer. This is a bottleneck for keeping the support information current.
*   **Recommendation:**
    *   Build a simple, separate admin interface (could be another Streamlit app) that allows non-technical users to add, edit, and delete articles in the knowledge base.
    *   This interface would update the underlying data source (which could be evolved from a JSON file to a proper database) and trigger the re-embedding process for the updated content.
