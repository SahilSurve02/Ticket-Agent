import chromadb
from chromadb.config import Settings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
import os
from typing import List, Dict, Optional
from pydantic import BaseModel, Field
from src.state import AgentState
from dotenv import load_dotenv
load_dotenv()

llm = ChatOpenAI(
    model="gpt-4o-mini",
    temperature=0)

# Global KB instance (initialized at startup)
_global_kb = None

def set_global_kb(kb):
    """Set the global knowledge base instance"""
    global _global_kb
    _global_kb = kb

def get_global_kb():
    """Get the global knowledge base instance"""
    return _global_kb


class KnowledgeBase:
    def __init__(self, persist_directory: str = "./chroma_db"):
        self.persist_directory = persist_directory
        self.embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
        
        # Initialize ChromaDB with persistence
        self.vectorstore = Chroma(
            collection_name="it_support_kb",
            embedding_function=self.embeddings,
            persist_directory=persist_directory
        )

class KBDocument(BaseModel):
    """Knowledge Base Document Schema"""
    title: str = Field(description="Title of the article/solution")
    category: str = Field(description="Category: WiFi, Login, Hardware, Software, etc.")
    issue_type: str = Field(description="Specific issue type")
    symptoms: List[str] = Field(description="Common symptoms users report")
    solution: str = Field(description="Step-by-step solution")
    severity: str = Field(description="Low, Medium, High, Critical")
    related_errors: List[str] = Field(default_factory=list, description="Error messages")
    prerequisites: List[str] = Field(default_factory=list, description="Requirements to apply solution")
    success_rate: Optional[float] = Field(default=None, description="Historical success rate")
    estimated_time: Optional[str] = Field(default=None, description="Time to resolve")


def load_knowledge_base(kb: KnowledgeBase, json_file: str):
    """Load knowledge documents from JSON file"""
    import json
    
    with open(json_file, 'r') as f:
        documents = json.load(f)
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=["\n\n", "\n", " ", ""]
    )
    
    for doc in documents:
        # Create rich text representation for embedding
        text_content = f"""
        Title: {doc['title']}
        Category: {doc['category']}
        Issue Type: {doc['issue_type']}
        Symptoms: {', '.join(doc['symptoms'])}
        Solution: {doc['solution']}
        Severity: {doc['severity']}
        Related Errors: {', '.join(doc.get('related_errors', []))}
        Estimated Time: {doc.get('estimated_time', 'N/A')}
        """
        
        # Split if too long
        chunks = text_splitter.split_text(text_content)
        
        # Store with metadata
        metadata = {
            "title": doc['title'],
            "category": doc['category'],
            "severity": doc['severity'],
            "success_rate": doc.get('success_rate', 0.0)
        }
        
        kb.vectorstore.add_texts(
            texts=chunks,
            metadatas=[metadata] * len(chunks)
        )

def search_knowledge(
    kb: KnowledgeBase,
    query: str,
    category: Optional[str] = None,
    top_k: int = 3,
    min_similarity: float = 0.5
) -> List[Dict]:
    """
    Search knowledge base with semantic similarity
    
    Args:
        kb: KnowledgeBase instance
        query: User's issue description
        category: Filter by category (WiFi, Login, Hardware)
        top_k: Number of results to return
        min_similarity: Minimum similarity threshold (0-1)
    
    Returns:
        List of relevant documents with metadata
    """
    # Build filter
    where_filter = {}
    if category:
        where_filter["category"] = category
    
    # Perform similarity search
    results = kb.vectorstore.similarity_search_with_score(
        query=query,
        k=top_k,
        filter=where_filter if where_filter else None
    )
    
    # Filter by minimum similarity and format results
    formatted_results = []
    for doc, score in results:
        # ChromaDB with langchain returns L2 distance
        # Lower score = more similar. Score of 0 = identical, Score > 1 = less similar
        # Convert to similarity: use exponential decay for better distribution
        # similarity = exp(-score) gives us 1.0 for score=0, ~0.37 for score=1
        import math
        similarity = math.exp(-score)
        
        # Debug: print score info
        print(f"[DEBUG] KB result: L2_dist={score:.4f}, similarity={similarity:.4f}")
        
        if similarity >= min_similarity:
            formatted_results.append({
                "content": doc.page_content,
                "metadata": doc.metadata,
                "similarity": similarity
            })
    
    return formatted_results


def get_best_solution(
    kb: KnowledgeBase,
    issue_description: str,
    conversation_history: List[str],
    category: Optional[str] = None
) -> Dict:
    """
    Get best solution with fallback strategies
    
    Returns:
        {
            "found": bool,
            "solutions": List[Dict],
            "confidence": str,  # "high", "medium", "low"
            "fallback_used": bool
        }
    """
    # Strategy 1: Direct semantic search (with category if available)
    results = search_knowledge(kb, issue_description, category, top_k=3, min_similarity=0.3)
    
    if results and results[0]["similarity"] >= 0.5:
        return {
            "found": True,
            "solutions": results,
            "confidence": "high",
            "fallback_used": False
        }
    
    # Strategy 2: Search without category filter
    if category:
        results = search_knowledge(kb, issue_description, category=None, top_k=5, min_similarity=0.3)
        
        if results and results[0]["similarity"] >= 0.4:
            return {
                "found": True,
                "solutions": results[:3],
                "confidence": "medium",
                "fallback_used": True
            }
    
    # Strategy 3: Use conversation context
    if conversation_history:
        context = " ".join(conversation_history[-5:])  # Last 5 messages
        enhanced_query = f"{issue_description} {context}"
        results = search_knowledge(kb, enhanced_query, category=None, top_k=5, min_similarity=0.3)
        
        if results and results[0]["similarity"] >= 0.35:
            return {
                "found": True,
                "solutions": results[:3],
                "confidence": "medium",
                "fallback_used": True
            }
    
    # Strategy 4: No good match
    return {
        "found": False,
        "solutions": [],
        "confidence": "low",
        "fallback_used": True
    }

# def chatbot_node_with_rag(state: AgentState):
#     """Enhanced chatbot with knowledge base integration"""
#     messages = state["messages"]
#     kb = state.get("knowledge_base")  # Add to state
    
#     # Extract user's issue from latest message
#     user_message = messages[-1].content if messages else ""
    
#     # Detect category from conversation
#     category = detect_category(user_message)  # Helper function
    
#     # Search knowledge base
#     if kb:
#         kb_results = get_best_solution(
#             kb=kb,
#             issue_description=user_message,
#             conversation_history=[m.content for m in messages[:-1]],
#             category=category
#         )
#     else:
#         kb_results = {"found": False, "solutions": []}
    
#     # Build enhanced system prompt with RAG context
#     if kb_results["found"] and kb_results["confidence"] in ["high", "medium"]:
#         # Format KB solutions for LLM
#         kb_context = "\n\n".join([
#             f"**Solution {i+1}** (Similarity: {sol['similarity']:.2%}):\n{sol['content']}"
#             for i, sol in enumerate(kb_results["solutions"])
#         ])
        
#         system_prompt = f"""
#         You are an IT Support Chatbot with access to a knowledge base.
        
#         RELEVANT SOLUTIONS FROM KNOWLEDGE BASE:
#         {kb_context}
        
#         INSTRUCTIONS:
#         1. Use the provided solutions as a reference
#         2. Adapt the steps to the user's specific situation
#         3. Be conversational and empathetic
#         4. If the user confirms the issue is resolved, thank them
#         5. If the user says "it didn't work" or requests a ticket, reply with "handoff_to_ticket"
#         6. Ask clarifying questions if needed
        
#         Keep responses concise and actionable.
#         """
#     else:
#         # Fallback to generic prompt
#         system_prompt = """
#         You are an IT Support Chatbot.
#         1. Provide general troubleshooting steps for: WiFi, Login, Hardware issues
#         2. If the user says "it didn't work" or asks for a ticket, reply with "handoff_to_ticket"
#         3. Be helpful and ask clarifying questions
        
#         Note: I couldn't find a specific solution in the knowledge base, so provide general advice.
#         """
    
#     # Invoke LLM with enhanced context
#     response = llm.invoke([SystemMessage(content=system_prompt)] + messages)
    
#     # Update state with KB metadata
#     return {
#         "messages": [response],
#         "kb_used": kb_results["found"],
#         "kb_confidence": kb_results.get("confidence", "none")
#     }

def detect_category(message: str) -> Optional[str]:
    """Detect issue category from user message - returns category matching KB and form templates"""
    message_lower = message.lower()
    
    # Categories now match KB and form templates
    categories = {
        "Network": ["wifi", "wireless", "internet", "connection", "network", "router", "vpn", "ethernet", "connected"],
        "Account": ["login", "password", "account", "locked", "authentication", "credentials", "mfa", "2fa", "sign in", "sign-in"],
        "Hardware": ["slow", "performance", "freeze", "crash", "hardware", "laptop", "computer", "monitor", "keyboard", "mouse", "battery", "screen", "display", "audio", "sound", "printer"],
        "Software": ["application", "program", "software", "install", "update", "app", "office", "word", "excel", "windows update"],
        "Email": ["email", "outlook", "mail", "inbox", "sending", "receiving", "emails"]
    }
    
    for category, keywords in categories.items():
        if any(keyword in message_lower for keyword in keywords):
            return category
    
    return "General"

class KnowledgeBaseError(Exception):
    """Custom exception for KB operations"""
    pass

def safe_kb_search(kb: KnowledgeBase, query: str, **kwargs) -> Dict:
    """KB search with error handling"""
    try:
        if not kb or not kb.vectorstore:
            raise KnowledgeBaseError("Knowledge base not initialized")
        
        results = search_knowledge(kb, query, **kwargs)
        return {"success": True, "data": results, "error": None}
        
    except Exception as e:
        # Log error (use loguru)
        # logger.error(f"KB search failed: {str(e)}")
        return {
            "success": False,
            "data": [],
            "error": str(e)
        }
    
def initialize_kb_with_check(persist_directory: str) -> Optional[KnowledgeBase]:
    """Initialize KB with validation"""
    try:
        kb = KnowledgeBase(persist_directory)
        
        # Check if KB has documents
        collection = kb.vectorstore._collection
        if collection.count() == 0:
            # logger.warning("Knowledge base is empty. Loading default documents...")
            load_knowledge_base(kb, "data/kb.json")
        
        return kb
        
    except FileNotFoundError:
        # logger.error("Knowledge base data file not found")
        return None
    except Exception as e:
        # logger.error(f"Failed to initialize KB: {str(e)}")
        return None
    
def refresh_kb_if_needed(kb: KnowledgeBase, max_age_days: int = 30) -> bool:
    """Check if KB needs refresh based on age"""
    import datetime
    from pathlib import Path
    
    db_path = Path(kb.persist_directory)
    if not db_path.exists():
        return False
    
    # Check last modified time
    modified_time = datetime.datetime.fromtimestamp(db_path.stat().st_mtime)
    age = (datetime.datetime.now() - modified_time).days
    
    if age > max_age_days:
        # logger.info(f"Knowledge base is {age} days old, consider refreshing")
        return True
    
    return False