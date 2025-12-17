from langgraph.graph import StateGraph, END, START
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from src.state import AgentState, TicketSchema
from src.nodes import chatbot_node, ticket_agent_node
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
    Decides if we stay in Chatbot mode or move to Ticket Agent.
    """
    last_msg = state["messages"][-1]
    
    # If the chatbot said the magic word "handoff_to_ticket" (or you can use a structured flag)
    if "handoff_to_ticket" in last_msg.content:
        return "ticket_agent"
    return END # Or wait for user input

def route_ticket(state: AgentState):
    """
    Loops the ticket agent until the form is complete.
    """
    ticket = state["ticket"]
    # Handle both dict and TicketSchema instances
    is_complete = ticket.get("is_complete") if isinstance(ticket, dict) else ticket.is_complete
    
    if is_complete:
        return "submit_ticket"
    return "continue_filling" # Loop back to ticket_agent

# 2. Build the Graph
workflow = StateGraph(AgentState)

# Add Nodes
workflow.add_node("chatbot", chatbot_node)
workflow.add_node("ticket_agent", ticket_agent_node)
workflow.add_node("submit_ticket", lambda state: {"messages": [AIMessage(content="Ticket #1234 Created!")]})

# Set Entry Point
workflow.set_entry_point("chatbot")

# Add Edges
# From Chatbot -> User Input OR Ticket Agent
workflow.add_conditional_edges(
    "chatbot",
    route_chatbot,
    {
        "ticket_agent": "ticket_agent",
        END: END
    }
)

# From Ticket Agent -> Loop OR Submit
workflow.add_conditional_edges(
    "ticket_agent", 
    route_ticket,
    {
        "continue_filling": "ticket_agent", # The Loop
        "submit_ticket": "submit_ticket"
    }
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
        "ticket": {"issue_summary": None, "is_complete": False}
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
                
                # Check if this node produced a new AI message
                if "messages" in state_update and state_update["messages"]:
                    last_msg = state_update["messages"][-1]
                    print(f"\n[{node_name}]: {last_msg.content}")
                
                # Optional: Print ticket updates if they happen
                if "ticket" in state_update:
                    print(f"   (Ticket State Updated: {state_update['ticket']})")


if __name__ == "__main__":
    # Ensure you are using a Checkpointer so state is remembered!
    
    # RE-COMPILE with memory (Important!)
    memory = MemorySaver()
    app = workflow.compile(checkpointer=memory)
    
    run_chat()