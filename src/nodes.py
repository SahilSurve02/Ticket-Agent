from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel
from src.state import AgentState, TicketSchema
import os
from dotenv import load_dotenv
load_dotenv()

# Initialize LLM
llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

# --- NODE 1: The General Chatbot (Troubleshooter) ---
def chatbot_node(state: AgentState):
    messages = state["messages"]
    
    # Logic: simple heuristic or LLM decision to check if issue is resolved
    # For this demo, we ask the LLM to decide if it should route to ticket filing.
    
    system_prompt = """
    You are an IT Support Chatbot.
    1. specific Troubleshooting steps for: Wifi, Login, Hardware.
    2. If the user says "it didn't work" or asks for a ticket, reply with "handoff_to_ticket".
    3. Otherwise, be helpful and brief.
    """
    
    # We allow the LLM to just reply normally
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