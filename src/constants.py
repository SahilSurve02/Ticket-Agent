"""
Constants and Configuration for IT Support System
Centralizes all magic numbers, valid values, and thresholds
"""

# =============================================================================
# VALID VALUES - Used for validation
# =============================================================================

VALID_CATEGORIES = [
    "Network", 
    "Account", 
    "Hardware", 
    "Software", 
    "Email", 
    "General", 
    "OUT_OF_SCOPE"
]

VALID_PRIORITIES = [
    "Low", 
    "Medium", 
    "High", 
    "Critical"
]

# Priority aliases for normalization
PRIORITY_ALIASES = {
    "urgent": "High",
    "emergency": "Critical",
    "asap": "High",
    "normal": "Medium",
    "minor": "Low",
    "low": "Low",
    "medium": "Medium",
    "med": "Medium",
    "high": "High",
    "critical": "Critical",
    "crit": "Critical",
    "l": "Low",
    "m": "Medium",
    "h": "High",
    "c": "Critical",
    "1": "Low",
    "2": "Medium",
    "3": "High",
    "4": "Critical"
}

# =============================================================================
# CONFIDENCE THRESHOLDS
# =============================================================================

# Default threshold for all extractions
DEFAULT_CONFIDENCE_THRESHOLD = 0.5

# Per-field thresholds (can be tuned independently)
FIELD_CONFIDENCE_THRESHOLDS = {
    "priority": 0.5,      # Lower threshold OK for priority (semantic)
    "device_id": 0.6,     # Higher threshold for device (more critical)
    "category": 0.5,      # Medium threshold for category
    "issue_summary": 0.4  # Lower threshold for summary
}

# =============================================================================
# LLM CONFIGURATION
# =============================================================================

LLM_MODEL = "gpt-4.1-mini"
LLM_TEMPERATURE = 0  # Deterministic outputs

# =============================================================================
# CONTEXT WINDOW CONFIGURATION
# =============================================================================

ROUTER_MAX_MESSAGES = 8       # Max messages for LLM router context
ROUTER_INITIAL_CONTEXT = 3    # First N messages to keep
ROUTER_RECENT_CONTEXT = 5     # Last N messages to keep
EXTRACTION_MAX_MESSAGES = 10  # Max messages for field extraction

# =============================================================================
# USER RESPONSE KEYWORDS
# =============================================================================

AFFIRMATIVE_WORDS = [
    "yes", "yeah", "yep", "sure", "ok", "okay", "please", "yup", 
    "create", "go ahead", "do it", "confirm", "proceed"
]

NEGATIVE_WORDS = [
    "no", "nope", "nah", "cancel", "nevermind", "never mind", 
    "don't", "do not", "stop", "not now", "later", "skip"
]

SUBMIT_WORDS = [
    "submit", "yes", "confirm", "ok", "proceed", "create"
]

EDIT_WORDS = [
    "edit", "change", "modify", "update"
]

CANCEL_WORDS = [
    "cancel", "no", "nevermind", "back", "stop"
]
