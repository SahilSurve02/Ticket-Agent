# ChatbotAgent & TicketAgent - Backend Analysis

> **Created:** January 1, 2026  
> **Scope:** ChatbotAgent and TicketAgent Backend ONLY  
> **Files:** `agents.py`, `nodes.py`, `router.py`, `state.py`

---

## 📊 Summary

| Status | Count | % |
|--------|-------|---|
| ✅ **Done** | 12 | ~65% |
| 🟡 **Partial** | 4 | ~22% |
| ❌ **Missing** | 2 | ~13% |

**Overall:** ChatbotAgent and TicketAgent are well-implemented with industry-standard patterns. Core flows work correctly.

---

## 1. CHATBOT AGENT ✅

### 1.1 Core Features

| Feature | Status | Implementation |
|---------|--------|----------------|
| KB Search & Troubleshooting | ✅ | `get_best_solution()` with semantic search |
| Greeting Handling | ✅ | System prompt handles greetings |
| IT Scope Validation | ✅ | `_check_it_scope()` - LLM domain filter |
| Escalation to Ticket | ✅ | Structured `escalate_to_ticket` flag |
| Ticket Confirmation | ✅ | "Create ticket?" (yes/no) flow |
| Ambiguous Feedback | ✅ | `_is_ambiguous_feedback()` detection |

---

### 1.2 Entity Extraction ✅

| Entity | Status | Method |
|--------|--------|--------|
| Category | ✅ | LLM-based `detect_category()` |
| Priority | ✅ | Semantic inference ("urgent" → High) |
| Device | ✅ | LLM matching to registered devices |
| Issue Summary | ✅ | Auto-extracted by TicketAgent |

**Strength:** Uses Pydantic `ExtractedTicketFields` for structured output. Semantic understanding (e.g., "box is toast" → Hardware/Critical).

```python
class ExtractedTicketFields(BaseModel):
    category: Optional[str]
    priority: Optional[str]
    device_type: Optional[str]
    device_brand: Optional[str]
    confidence: float
```

---

### 1.3 Handoff Mechanism ✅

| Aspect | Status |
|--------|--------|
| Structured Flag | ✅ `escalate_to_ticket: bool` |
| Deterministic Routing | ✅ No string matching |
| Category Preservation | ✅ Passed to TicketAgent |

**Industry-Standard:** Uses `ChatbotResponseAction` schema for deterministic handoff.

---

### 1.4 Out-of-Scope Handling ✅

- ✅ LLM-based domain classification
- ✅ Rejects travel, food, shopping requests
- ✅ Allows IT + general conversation
- ✅ Handles edge cases ("book a ticket for laptop" = IT)

---

### 1.5 Knowledge Base ✅

| Feature | Status |
|---------|--------|
| Semantic Search | ✅ ChromaDB |
| Confidence Thresholds | ✅ High/Medium/Low |
| Fallback Strategies | ✅ Multiple attempts |

---

## 2. TICKET AGENT ✅

### 2.1 Core Features

| Feature | Status |
|---------|--------|
| Step-by-Step Collection | ✅ category → device → priority → description |
| Category-Specific Fields | ✅ `FORM_TEMPLATES` |
| Field Validation | ✅ Retry on invalid input |
| Edit Mode | ✅ Modify before submit |
| Preview Generation | ✅ Markdown preview |
| Submit/Cancel | ✅ Full flow |

---

### 2.2 Collection Flow ✅

```
Escalate → Category → Device → Priority → Description → [Extras] → Preview → Submit
              ↓          ↓         ↓            ↓
         (auto-detect) (auto-    (inferred)   (from chat)
                       select)
```

**Auto-Fill:**
- ✅ Category from ChatbotAgent
- ✅ Device auto-select (if only 1)
- ✅ Priority from urgency signals
- ✅ Summary from conversation

---

### 2.3 Category Templates ✅

| Category | Extra Fields |
|----------|--------------|
| Network | connection_type, error_message |
| Account | account_type, last_working |
| Hardware | component, physical_damage |
| Software | application_name, error_code |
| Email | email_client, affected_action |
| General | (none) |

---

### 2.4 Device Matching ✅

| Feature | Status |
|---------|--------|
| Single Auto-Select | ✅ |
| LLM Matching | ✅ |
| Fuzzy Token Match | ✅ |
| Validation + Retry | ✅ |

---

### 2.5 Edit Mode ✅

- ✅ Trigger via "edit" command
- ✅ LLM extracts field changes
- ✅ Returns to preview after edit
- ✅ Preserves unedited fields

---

### 2.6 Validation 🟡

| Validation | Status |
|------------|--------|
| Required Fields | ✅ |
| Priority Values | ✅ |
| Device Selection | ✅ |
| Category Values | ✅ |
| Email Format | ❌ Not validated |
| Phone Format | ❌ Not validated |

---

## 3. ROUTING ✅

### 3.1 Dual-Mode

| Mode | Status | Use |
|------|--------|-----|
| Rule-Based | ✅ Default | Fast |
| LLM-Based | ✅ Opt-in | Complex intent |

---

### 3.2 Decisions

| From | To | Trigger |
|------|----|---------|
| chatbot | ticket_collection | `escalate_to_ticket=True` |
| chatbot | ticket_confirmation | `awaiting_confirmation=True` |
| ticket_collection | ticket_preview | All fields complete |
| ticket_confirmation | submit_ticket | User says "submit" |

---

## 4. 🟡 PARTIALLY DONE

### 4.1 Duplicate Detection 🟡

**Done:**
- ✅ `check_for_duplicate_ticket()` exists in db.py

**Missing:**
- ❌ Not called in ticket flow
- ❌ No "Add to existing or create new?" prompt

---

### 4.2 Topic Change Warning 🟡

**Missing (FR-007):**
- ❌ Detect topic change mid-conversation
- ❌ Warn before resetting form data

---

### 4.3 Request Type 🟡

**Current:** Category only (Network, Account, etc.)

**Missing:**
- ❌ Question vs Concern vs Complaint
- ❌ "Is this a Question or Concern?" prompt

---

### 4.4 Confidence Tracking 🟡

**Done:**
- ✅ KB has confidence thresholds

**Missing:**
- ❌ Per-field confidence tracking
- ❌ Visual indicator for medium-confidence

---

## 5. ❌ MISSING

### 5.1 User-Modified Field Protection ❌

**Requirement (FR-009):** Bot SHALL NOT overwrite user modifications.

**Current:** No `user_modified` flag. Bot might overwrite edited fields on re-extraction.

---

### 5.2 Acknowledgment Logic ❌

**Requirements:**
- FR-004: Acknowledge ALL fields on first interaction
- FR-005: Acknowledge ONLY changed fields on subsequent

**Current:** No differentiation between first vs subsequent.

---

## 6. 💡 RECOMMENDATIONS

### Quick Wins

| # | Action | Effort |
|---|--------|--------|
| 1 | **Wire duplicate detection** - Call before preview | Low |
| 2 | **Topic change detection** - Compare category, warn if different | Low |
| 3 | **Track field sources** - Add `field_sources: Dict` to state | Medium |

### Medium Effort

| # | Action |
|---|--------|
| 4 | Add `request_type` (Question/Concern/Complaint) to schema |
| 5 | Extract LLM prompts to `prompts.py` |
| 6 | Add email/phone format validation |

### Technical Debt

| Issue | Action |
|-------|--------|
| Inline prompts | Move to templates file |
| Magic strings | Create constants for categories/priorities |
| No tests | Add unit tests for agents |

---

## 7. 📍 WHERE ARE WE?

### Agent Implementation: **~80% Complete**

```
[████████████████████░░░░] 80%

✅ DONE:
   - ChatbotAgent core flow
   - TicketAgent core flow
   - Entity extraction (LLM-based)
   - Category/Priority detection
   - Device matching
   - Edit mode
   - Preview/Submit flow
   - Routing logic

🟡 NEEDS WORK:
   - Duplicate detection call
   - Topic change warning
   - Field source tracking

❌ MISSING:
   - User-modified field protection
   - First/subsequent acknowledgment
```

---

## 8. APPROACH ANALYSIS

### ✅ What's Good

1. **Structured LLM Outputs** - Pydantic schemas ensure reliable parsing
2. **Semantic Extraction** - LLM understands "box is toast" = Critical
3. **Clean Agent Separation** - ChatbotAgent ≠ TicketAgent
4. **Deterministic Handoff** - Flags, not string matching
5. **Exception Handling** - Try/catch throughout with logging

### ⚠️ Concerns

1. **No Field Protection** - User edits can be overwritten
2. **Duplicate Check Unused** - Function exists but not called
3. **Inline Prompts** - Hard to maintain/test

---

## 9. FILES

| File | Contains | Status |
|------|----------|--------|
| [agents.py](../src/agents.py) | ChatbotAgent, TicketAgent | ✅ |
| [nodes.py](../src/nodes.py) | Node wrappers | ✅ |
| [router.py](../src/router.py) | LLMRouter | ✅ |
| [state.py](../src/state.py) | Schemas | ✅ |

---

*Focused analysis of ChatbotAgent and TicketAgent backend only.*
