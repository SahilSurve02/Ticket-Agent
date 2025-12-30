"""
IT Support Chatbot - CLI Entry Point

This is the command-line interface for the IT Support Chatbot.
It uses the unified workflow graph from src/graph.py.
"""

import uuid
import traceback
import logging
from langgraph.checkpoint.memory import MemorySaver
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv

from src.state import create_empty_ticket
from src.kb import initialize_kb_with_check, set_global_kb
from src.db import init_db
from src.graph import (
    build_workflow,
    compile_workflow,
    create_initial_state,
    setup_logging
)

load_dotenv()

# Setup logging
setup_logging(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# MAIN CHAT FUNCTION
# =============================================================================

def run_chat():
    """
    Main chat loop for CLI interaction.
    
    Initializes the database, knowledge base, and workflow graph,
    then runs an interactive chat session with the user.
    """
    # Initialize DB
    try:
        init_db()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        print(f"⚠ Warning: Database initialization failed: {e}")

    # Initialize KB
    kb = None
    try:
        kb = initialize_kb_with_check("./chroma_db")
        set_global_kb(kb)
        if kb:
            print("✓ Knowledge base initialized successfully")
            logger.info("Knowledge base initialized successfully")
        else:
            print("⚠ Warning: Running without knowledge base")
            logger.warning("Running without knowledge base")
    except Exception as e:
        logger.error(f"Failed to initialize knowledge base: {e}")
        print(f"⚠ Warning: Knowledge base initialization failed: {e}")
    
    # Simulated user info (would come from login session in production)
    user_info = {
        "user_id": "EMP-12345",
        "user_name": "Krishna Ronaldo",
        "email": "krishna.ronaldo@company.com",
        "phone": "+1-777-0123",
        "department": "Engineering"
    }
    
    user_devices = [
        "Dell Latitude 5420", 
        "iPad Pro", 
        "iPhone 14", 
        "MacBook Pro", 
        "HP Printer LaserJet 200"
    ]
    
    # Initial state
    initial_input = create_initial_state(user_info, user_devices)
    
    # Setup workflow
    try:
        thread_id = str(uuid.uuid4())
        config = {"configurable": {"thread_id": thread_id}}
        memory = MemorySaver()
        
        workflow = build_workflow()
        app = compile_workflow(workflow, checkpointer=memory)
        
        logger.info("Workflow initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize workflow: {e}")
        print(f"✗ Failed to initialize workflow: {e}")
        return
    
    print("\n" + "="*60)
    print("IT SUPPORT CHATBOT")
    print("="*60)
    print(f"Logged in as: {user_info['user_name']} ({user_info['email']})")
    print("Type 'q' to quit")
    print("="*60 + "\n")
    
    first_turn = True
    
    while True:
        try:
            user_text = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break
        
        if user_text.lower() in ["q", "quit", "exit"]:
            print("\nGoodbye!")
            break
        
        if not user_text:
            continue
        
        # Build input
        input_message = {"messages": [HumanMessage(content=user_text)]}
        
        # First turn: include initial state
        if first_turn:
            input_message.update(initial_input)
            first_turn = False
        
        # Process through graph
        try:
            for event in app.stream(input_message, config=config):
                for node_name, state_update in event.items():
                    if not state_update:
                        continue
                    
                    if "messages" in state_update and state_update["messages"]:
                        last_msg = state_update["messages"][-1]
                        # Don't print agent handoff signals to user
                        if hasattr(last_msg, 'content'):
                            content = last_msg.content
                            if "HANDOFF_TO_TICKET_AGENT" not in content and "handoff_to_ticket" not in content:
                                print(f"\nBot: {content}")
        
        except KeyboardInterrupt:
            print("\n\nInterrupted. Goodbye!")
            break
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)
            print(f"\n[Error]: {e}")
            if logger.isEnabledFor(logging.DEBUG):
                traceback.print_exc()


if __name__ == "__main__":
    run_chat()
