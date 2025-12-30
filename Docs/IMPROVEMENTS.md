# IT Support Chatbot - Improvements and Recommendations

This document outlines identified issues, prompt improvements, and cleanup recommendations for production deployment.

---

## Table of Contents
1. [Critical Issue: Premature Solution Provision](#critical-issue-premature-solution-provision)
2. [Prompt Improvements](#prompt-improvements)
3. [Code Cleanup Recommendations](#code-cleanup-recommendations)
4. [Threshold Adjustments](#threshold-adjustments)
5. [Recommended Fixes](#recommended-fixes)

---

## Critical Issue: Premature Solution Provision

### Problem Description
When a user says something vague like *"I am struggling with my laptop please help me with that"*, the chatbot immediately provides specific troubleshooting steps (e.g., for overheating) without first asking clarifying questions to understand the actual issue.

### Root Causes

#### 1. Low Similarity Thresholds
**File:** `src/kb.py`

| Threshold | Current Value | Issue |
|-----------|---------------|-------|
| `min_similarity` | 0.25 | Too permissive - matches almost anything |
| High confidence | 0.4 | Too low - vague queries get "high" confidence |
| Medium confidence | 0.35 | Allows false positives |

```python
# Current (problematic)
results = search_knowledge(kb, issue_description, category, top_k=3, min_similarity=0.25)

if results and results[0]["similarity"] >= 0.4:  # Too low for "high" confidence
    return {"found": True, "solutions": results, "confidence": "high", ...}
```

#### 2. System Prompt Doesn't Require Clarification
**File:** `src/agents.py` (lines 240-270)

The current system prompt instructs the chatbot to provide solutions immediately when KB results are found, without checking if the query is specific enough.

```python
# Current prompt (problematic)
system_prompt = f"""You are the IT Support Chatbot Agent.

KNOWLEDGE BASE SOLUTIONS:
{kb_context}

YOUR ROLE:
1. Provide clear troubleshooting steps from the knowledge base.
2. Format as numbered list
3. Ask: "Let me know if this helps!"
...
"""
```

**Issue:** The prompt says "Provide clear troubleshooting steps" unconditionally when KB results exist.

#### 3. Semantic Similarity with Vague Queries
When the user mentions "laptop" without specifying the issue:
- The embedding model finds articles containing "laptop" (e.g., "Slow Computer Performance", "Computer Freezing", "Laptop Overheating")
- With low thresholds (0.25-0.4), these get classified as "high confidence" matches
- The chatbot provides solutions without understanding the actual problem

---

## Prompt Improvements

### 1. ChatbotAgent System Prompt (High Confidence KB Results)

**Current (problematic):**
```python
system_prompt = f"""You are the IT Support Chatbot Agent.

KNOWLEDGE BASE SOLUTIONS:
{kb_context}

YOUR ROLE:
1. Provide clear troubleshooting steps from the knowledge base.
2. Format as numbered list
3. Ask: "Let me know if this helps!"

Keep responses SHORT and solution-focused.
DO NOT mention tickets or escalation - I handle that separately.
"""
```

**Recommended:**
```python
system_prompt = f"""You are the IT Support Chatbot Agent.

KNOWLEDGE BASE SOLUTIONS (for reference):
{kb_context}

CRITICAL RULES:
1. FIRST check if the user's message clearly specifies their issue
2. If the query is VAGUE (e.g., "laptop issue", "need help", "having problems"):
   - DO NOT provide specific solutions yet
   - ASK a clarifying question: "I'd be happy to help! Could you describe what specific issue you're experiencing with your laptop? For example: is it running slow, not turning on, having display issues, etc.?"
3. ONLY provide troubleshooting steps when you clearly understand the specific problem
4. When providing solutions, format as numbered list and ask "Let me know if this helps!"

EXAMPLES OF VAGUE QUERIES (ask for clarification):
- "My laptop has issues"
- "I'm struggling with my computer"
- "Need help with device"
- "Having problems"

EXAMPLES OF SPECIFIC QUERIES (provide solutions):
- "My laptop is running very slow"
- "WiFi keeps disconnecting"
- "Can't login to my account"
- "Blue screen error on startup"

Keep responses SHORT and helpful.
DO NOT mention tickets or escalation - I handle that separately.
"""
```

### 2. ChatbotAgent System Prompt (Low/No KB Results)

**Current:**
```python
system_prompt = """You are the IT Support Chatbot Agent.

YOUR ROLE:
1. Do not provide solutions from your knowledge base.
2. Say: "I couldn't find a specific solution, could you please provide more details about the issue?"

Keep responses SHORT and helpful.
DO NOT mention tickets or escalation - I handle that separately.
"""
```

**Recommended:**
```python
system_prompt = """You are the IT Support Chatbot Agent.

YOUR ROLE:
1. Ask clarifying questions to understand the user's specific issue
2. Be conversational and empathetic
3. Examples of good clarifying questions:
   - "Could you describe what's happening when you try to use your laptop?"
   - "Is this a new issue or has it been happening for a while?"
   - "Are there any error messages appearing?"

Keep responses SHORT and helpful.
DO NOT mention tickets or escalation - I handle that separately.
"""
```

### 3. Add Query Specificity Check

**New helper method for ChatbotAgent:**
```python
def _is_query_specific(self, user_message: str) -> bool:
    """
    Check if the user query is specific enough to provide solutions.
    Returns True if specific, False if too vague.
    """
    system_prompt = """Analyze if this IT support query is SPECIFIC enough to provide solutions.

SPECIFIC queries clearly indicate:
- What device/software has the issue
- What the actual problem/symptom is
- What behavior they're experiencing

VAGUE queries are:
- Generic requests for help
- No clear symptom or error described
- Only mention a device without describing the issue

Respond with JSON: {"specific": true/false, "reason": "brief explanation"}"""

    try:
        result = self.llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=f"Query: {user_message}")
        ])
        # Parse response and return
        import json
        parsed = json.loads(result.content)
        return parsed.get("specific", False)
    except:
        return False  # Default to asking clarification
```

---

## Code Cleanup Recommendations

### 1. Remaining Print Statements → Convert to Logging

**Files affected:** `src/agents.py`

The following `print()` statements should be converted to `logger` calls:

| Line | Current | Recommended |
|------|---------|-------------|
| 346 | `print(f"[ChatbotAgent] Scope check...")` | `logger.debug(f"Scope check...")` |
| 350 | `print(f"[ChatbotAgent] Scope check error...")` | `logger.warning(f"Scope check error...")` |
| 445-449 | Device matching prints | `logger.debug(...)` |
| 451 | LLM extraction result | `logger.debug(...)` |
| 455 | LLM extraction error | `logger.warning(...)` |
| 568-571 | TicketAgent change extraction | `logger.debug(...)` |
| 671-703 | Device/Priority validation | `logger.debug(...)` |
| 784-791 | Auto-detection logs | `logger.debug(...)` |
| 815-858 | Extraction context logs | `logger.debug(...)` |

### 2. Commented-Out Code → Remove

**File:** `src/kb.py` (lines 238-302)

Remove the large commented-out `chatbot_node_with_rag` function that's no longer used:
```python
# def chatbot_node_with_rag(state: AgentState):
#     """Enhanced chatbot with knowledge base integration"""
#     ... (64 lines of dead code)
```

### 3. Duplicate/Unused Imports

Check and remove any unused imports across files after refactoring.

---

## Threshold Adjustments

### Recommended Changes for `src/kb.py`

```python
# File: src/kb.py - get_best_solution()

# BEFORE (too permissive)
results = search_knowledge(kb, issue_description, category, top_k=3, min_similarity=0.25)
if results and results[0]["similarity"] >= 0.4:
    return {"found": True, "solutions": results, "confidence": "high", ...}

# AFTER (more selective)
results = search_knowledge(kb, issue_description, category, top_k=3, min_similarity=0.45)
if results and results[0]["similarity"] >= 0.6:
    return {"found": True, "solutions": results, "confidence": "high", ...}

# For medium confidence
if results and results[0]["similarity"] >= 0.5:
    return {"found": True, "solutions": results[:3], "confidence": "medium", ...}
```

| Threshold | Current | Recommended | Rationale |
|-----------|---------|-------------|-----------|
| `min_similarity` | 0.25 | 0.45 | Filter out weak matches |
| High confidence | 0.40 | 0.60 | Ensure strong match before providing solutions |
| Medium confidence | 0.35 | 0.50 | Reduce false positives |

---

## Recommended Fixes

### Priority 1: Fix Premature Solution Issue

1. **Update `get_best_solution()` thresholds** in `src/kb.py`
2. **Update ChatbotAgent system prompts** to require clarification for vague queries
3. **Add `_is_query_specific()` check** before providing KB solutions

### Priority 2: Code Cleanup

1. Convert all `print()` statements to `logger` calls
2. Remove commented-out code in `src/kb.py`
3. Clean up unused imports

### Priority 3: Testing

1. Test with vague queries:
   - "I need help with my laptop"
   - "Having computer problems"
   - "My device isn't working"
2. Test with specific queries:
   - "My laptop is running very slow and freezing"
   - "WiFi keeps disconnecting every 5 minutes"
   - "Can't login - getting wrong password error"

---

## Implementation Checklist

- [x] Increase similarity thresholds in `kb.py` ✅ (Done: min_similarity 0.25→0.45, high confidence 0.4→0.6, medium confidence 0.35→0.50)
- [x] Update ChatbotAgent prompts to require clarification ✅ (Done: Added CRITICAL RULES for vague query detection)
- [ ] Add query specificity check (Optional - prompts now handle this)
- [x] Convert print statements to logging ✅ (Done: All prints now use logger.info/debug/warning)
- [x] Logs saved to file ✅ (Done: Logs/app.log)
- [ ] Remove commented-out code in kb.py
- [ ] Test with vague and specific queries
- [ ] Update documentation

---

*Document generated: December 30, 2025*
*Last updated: December 30, 2025*
