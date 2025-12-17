from langgraph.graph import StateGraph, END, START
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.state import AgentState, TicketSchema
from src.nodes import chatbot_node, ticket_collection_node, ticket_confirmation_node, ticket_preview_node
from src.kb import initialize_kb_with_check
from langgraph.checkpoint.memory import MemorySaver
import uuid
from langchain_core.messages import HumanMessage
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
load_dotenv()

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0,
    api_key=os.getenv("OPENAI_API_KEY")
)


# 1. Define the Router Logic
def route_chatbot(state: AgentState):
    """
    Routes from chatbot to ticket collection or stays in chat
    """
    
    # Check if user is in confirmation phase (preview was shown, waiting for submit/edit/cancel)
    if state.get("awaiting_confirmation"):
        return "ticket_confirmation"
    
    # Check if we just asked a ticket question - route to ticket_collection
    last_question = state.get("last_question", None)
    if last_question in ["device", "priority", "description"]:
        return "ticket_collection"
    
    # Check if we have an incomplete ticket (user is in middle of filing)
    ticket = state.get("ticket", {})
    if isinstance(ticket, dict):
        has_summary = ticket.get("issue_summary") is not None
        has_device = ticket.get("device_id") is not None
        has_priority = ticket.get("priority") is not None
        has_description = ticket.get("description") is not None
        
        # If we have some fields but not all required ones
        if has_summary and not (has_device and has_priority and has_description):
            return "ticket_collection"
    
    last_msg = state["messages"][-1]
    
    if "handoff_to_ticket" in last_msg.content:
        return "ticket_collection"
    return END

def route_ticket_collection(state: AgentState):
    """
    Routes from ticket collection phase
    """
    current_ticket = state["ticket"]
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    # Check if ALL required fields are collected (including description)
    has_summary = current_ticket.issue_summary is not None
    has_device = current_ticket.device_id is not None
    has_priority = current_ticket.priority is not None
    has_description = current_ticket.description is not None
    
    if has_summary and has_device and has_priority and has_description:
        return "ticket_preview"
    else:
        return END  # Wait for user to respond with next field
    
def route_confirmation(state: AgentState):
    """
    Routes from confirmation node based on user's choice
    """
    confirmation_action = state.get("confirmation_action", "")
    
    if confirmation_action == "submit":
        return "submit_ticket"
    elif confirmation_action == "edit":
        return "ticket_collection"  # Go back to edit
    elif confirmation_action == "cancel":
        return "chatbot"  # Return to chatbot
    else:
        return END  # Invalid response, wait for valid input

# 2. Build the Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("ticket_collection", ticket_collection_node)
workflow.add_node("ticket_preview",ticket_preview_node)
workflow.add_node("ticket_confirmation", ticket_confirmation_node)
workflow.add_node("submit_ticket", lambda state: {
    "messages": [AIMessage(content="✅ Ticket #" + str(uuid.uuid4())[:8] + " created successfully!\n\nIs there anything else I can help you with?")],
    "ticket": {
        "issue_summary": None,
        "device_id": None,
        "priority": None,
        "description": None
    },
    "ticket_preview_shown": False,
    "awaiting_confirmation": False,
    "last_question": None
})
# Set Entry Point
workflow.set_entry_point("chatbot")

# Add Edges
# 1. From chatbot
workflow.add_conditional_edges(
    "chatbot",
    route_chatbot,
    {
        "ticket_collection": "ticket_collection",
        "ticket_confirmation": "ticket_confirmation",  # Route to confirmation when awaiting response
        END: END
    }
)

# 2. From ticket_collection
workflow.add_conditional_edges(
    "ticket_collection", 
    route_ticket_collection,
    {
        "ticket_preview": "ticket_preview",
        END: END  # Wait for user response instead of looping
    }
)

# 3. From ticket_preview -> END (wait for user to submit/edit/cancel)
# User's response will go to chatbot, which routes to ticket_confirmation
workflow.add_edge(
    "ticket_preview",
    END
)

# 4. From ticket_confirmation
workflow.add_conditional_edges(
    "ticket_confirmation",
    route_confirmation,
    {
        "submit_ticket": "submit_ticket",
        "ticket_collection": "ticket_collection",  # Edit
        "chatbot": "chatbot",  # Cancel
        END: END  # Invalid response, wait for valid input
    }
)

# 5. From submit_ticket -> END (ticket complete, wait for next user input)
workflow.add_edge(
    "submit_ticket", 
    END
)

# # Compile
memory = MemorySaver()
app = workflow.compile(checkpointer=memory)


def run_chat():
    # Initialize KB once at startup and set it globally
    from src.kb import set_global_kb
    kb = initialize_kb_with_check("./chroma_db")
    set_global_kb(kb)  # Store in global variable, not in state
    
    if not kb:
        print("Warning: Running without knowledge base")
    else:
        print("Knowledge base initialized successfully")
    
    initial_input = {
        "user_devices": ["Dell Latitude 5420", "iPad Pro"],
        "ticket": {
            "issue_summary": None, 
            "device_id": None,
            "priority": None,
            "description": None
        },
        "ticket_preview_shown": False,
        "awaiting_confirmation": False,
        "last_question": None
    }
    
    # 2. Config for the conversation thread (required by LangGraph to track state)
    # We use a static thread_id so the bot 'remembers' previous turns in this run
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("--- System: Chat Initialized (Type 'q' to quit) ---")
    
    while True:
        # 3. Get User Input
        user_text = input("\nUser: ")
        if user_text.lower() in ["q", "quit"]:
            print("Exiting...")
            break
            
        # 4. Stream the input into the graph
        # We only pass the NEW message; LangGraph handles history via the thread_id
        input_message = {"messages": [HumanMessage(content=user_text)]}
        
        # If this is the very first turn, we merge in our initial_input (devices, etc.)
        if "messages" not in initial_input: 
            # Slight hack for the very first message to inject the 'device' context
            input_message.update(initial_input)
            # Clear it so we don't re-inject next time
            initial_input["messages"] = True 

        # 5. Run the Graph and print responses
        # 'stream' yields events as nodes finish their work
        for event in app.stream(input_message, config=config):
            for node_name, state_update in event.items():
                
                # Skip if state_update is None or empty
                if not state_update:
                    continue
                
                # Check if this node produced a new AI message
                if "messages" in state_update and state_update["messages"]:
                    last_msg = state_update["messages"][-1]
                    print(f"\n[{node_name}]: {last_msg.content}")
                
                # Debug: Uncomment to see ticket updates during development
                # if "ticket" in state_update:
                #     print(f"   (Ticket State Updated: {state_update['ticket']})")


if __name__ == "__main__":
    # Ensure you are using a Checkpointer so state is remembered!
    
    # RE-COMPILE with memory (Important!)
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    run_chat()