# Test Flow Documentation

## Expected Flow for Ticket Creation

### Test Case 1: Complete Ticket Flow

**User Input Sequence:**
1. "Hi, my laptop is very slow"
2. "still not working" (after chatbot provides solution)
3. "yes" (when asked to create ticket)
4. "Dell" (when asked which device)
5. "High" (when asked for priority)
6. "no" (when asked for description)
7. "submit" (when shown preview)

**Expected Bot Responses:**

1. After "Hi, my laptop is very slow":
   - Provides troubleshooting steps from KB

2. After "still not working":
   - Asks: "Would you like me to create a support ticket for this issue?"

3. After "yes":
   - Says: "handoff_to_ticket"
   - ticket_collection asks: "Which device are you experiencing this issue with?"
   - Lists: Dell Latitude 5420, iPad Pro
   - **Should NOT show**: (Ticket State Updated: ...)
   - **Ticket state should be**: {issue_summary: "Laptop is very slow", device_id: None, priority: None, description: None}

4. After "Dell":
   - ticket_collection extracts device_id = "Dell Latitude 5420"
   - Asks: "What priority level should this ticket have?"
   - Lists priority options
   - **Should NOT auto-fill description**

5. After "High":
   - ticket_collection extracts priority = "High"
   - Asks: "Would you like to add any additional details?"

6. After "no":
   - ticket_collection sets description = "None provided"
   - Shows: "Great! Let me show you a preview of the ticket..."
   - Routes to ticket_preview

7. ticket_preview shows:
   ```
   📋 **Ticket Preview**
   
   **Issue Summary:** Laptop is very slow
   **Device:** Dell Latitude 5420
   **Priority:** High
   **Description:** None provided
   
   ---
   
   Options:
   - Type "submit" or "yes" to create the ticket
   - Type "edit" to make changes
   - Type "cancel" to cancel and return to chat
   
   What would you like to do?
   ```

8. After "submit":
   - Routes to ticket_confirmation
   - ticket_confirmation processes "submit"
   - Routes to submit_ticket
   - Shows: "✅ Ticket #[ID] created successfully!"

### Test Case 2: Cancel Flow

Same as above but:
- At step 7, user types "cancel"
- Should return to chatbot
- Ticket should be reset

### Test Case 3: Edit Flow

Same as above but:
- At step 7, user types "edit"
- Should ask: "What would you like to change?"
- Routes back to ticket_collection
- Can modify fields

## Critical Checks

✅ MUST ask for device (never auto-select)
✅ MUST ask for priority
✅ MUST NOT auto-fill description from conversation
✅ MUST show preview before submission
✅ MUST wait for confirmation
✅ MUST NOT show "(Ticket State Updated: ...)" to user
✅ issue_summary can be auto-extracted (only this field)

## Known Issues (FIXED)

- ❌ Device was being auto-selected → FIXED: Only extracts when last_question="device"
- ❌ Description was being auto-filled → FIXED: Strict field extraction
- ❌ Preview not shown → FIXED: Routing properly
- ❌ Ticket state shown to user → FIXED: Commented out debug print
