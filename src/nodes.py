from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.state import AgentState, TicketSchema
import os
from dotenv import load_dotenv
load_dotenv()


# Mock KB for "First Line of Defense" 
KB_ANSWERS = {
    "wifi": "1. Toggle Wifi on/off.\n2. Forget network 'SchoolWifi'.\n3. Restart device.",
    "login": "1. Clear browser cache.\n2. Try Incognito mode.\n3. Reset password."
}

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# --- NODE 1: The General Chatbot (Troubleshooter) ---
def chatbot_node(state: AgentState):
    messages = state["messages"]
    
    # Get KB from global scope (not from state, as it's not serializable)
    from src.kb import get_global_kb, get_best_solution, detect_category
    kb = get_global_kb()
    
    # Extract user's issue from latest message
    user_message = messages[-1].content if messages else ""
    
    # If KB is available, try to get relevant solutions
    kb_results = {"found": False, "solutions": []}
    if kb:
        try:
            category = detect_category(user_message)
            kb_results = get_best_solution(
                kb=kb,
                issue_description=user_message,
                conversation_history=[m.content for m in messages[:-1]],
                category=category
            )
        except Exception as e:
            # Fallback gracefully if KB fails
            print(f"Warning: KB search failed: {e}")
    
    # Build system prompt with or without KB context
    if kb_results["found"] and kb_results["confidence"] in ["high", "medium"]:
        # Format KB solutions for LLM
        kb_context = "\n\n".join([
            f"**Solution {i+1}** (Similarity: {sol['similarity']:.2%}):\n{sol['content']}"
            for i, sol in enumerate(kb_results["solutions"])
        ])
        
        system_prompt = f"""
        You are an IT Support Chatbot. 

        INSTRUCTIONS:
        1. Provide troubleshooting steps from the knowledge base and if don't get any relevant information from the knowledge base, let the user know you couldn't find anything useful.
        2. Keep responses concise - just the numbered steps and a little bit of explanation if needed and nothing distant from the original point.
        3. If user says "it didn't work", ask: "Would you like me to create a support ticket for this issue?"
        4. ONLY reply with "handoff_to_ticket" if user explicitly confirms they want a ticket (says yes, confirm, etc)
        5. If user says no, continue helping

        Do NOT automatically offer tickets. Only when user indicates solution didn't work.
        """
    else:
        # Fallback to generic prompt
        system_prompt = f"""
        You are an IT Support Chatbot. 

        INSTRUCTIONS:
        1. Provide troubleshooting steps from the knowledge base and if don't get any relevant information from the knowledge base, let the user know you couldn't find anything useful.
        2. Keep responses concise - just the numbered steps and a little bit of explanation if needed and nothing distant from the original point.
        3. If user says "it didn't work", ask: "Would you like me to create a support ticket for this issue?"
        4. ONLY reply with "handoff_to_ticket" if user explicitly confirms they want a ticket (says yes, confirm, etc)
        5. If user says no, continue helping

        Do NOT automatically offer tickets. Only when user indicates solution didn't work.
        """
    
    # Invoke LLM
    response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    
    return {"messages": [response]}


# --- NODE 2: The Ticket Agent (Form Filler) ---
def ticket_agent_node(state: AgentState):
    current_ticket = state["ticket"]
    # Convert dict to TicketSchema if needed
    if isinstance(current_ticket, dict):
        current_ticket = TicketSchema(**current_ticket)
    
    user_devices = state["user_devices"]
    
    # 1. DEFINE TOOLS for extraction
    # We use the schema to force the LLM to extract data
    llm_with_tools = llm.bind_tools([TicketSchema])
    
    # 2. CONSTRUCT PROMPT
    # We give the LLM the current form state so it knows what is missing
    system_prompt = f"""
    You are the Ticket Filing Agent.
    
    CURRENT TICKET STATE:
    {current_ticket.model_dump_json(exclude_none=True)}
    
    USER DEVICES: {user_devices}
    
    GOAL: Fill missing fields.
    1. If 'device_id' is missing and user has multiple devices, ask "Which device?".
    2. If 'issue_summary' is missing, extract it from history.
    3. If everything is found, set 'is_complete' to True.
    """
    
    response = llm_with_tools.invoke([SystemMessage(content=system_prompt)] + state["messages"])
    
    # 3. HANDLE UPDATES (Tool Calling)
    if response.tool_calls:
        # LLM wants to update the ticket!
        new_data = response.tool_calls[0]['args']
        updated_ticket = current_ticket.model_copy(update=new_data)
        
        # Create a ToolMessage to respond to the tool call
        tool_message = ToolMessage(
            content=f"Ticket updated successfully: {updated_ticket.model_dump_json(exclude_none=True)}",
            tool_call_id=response.tool_calls[0]['id']
        )
        
        # Return both the tool call message and the tool response
        return {
            "messages": [response, tool_message],
            "ticket": updated_ticket
        }
    
    # If no tool call, it's a question to the user (e.g. "What is your device?")
    return {"messages": [response]}