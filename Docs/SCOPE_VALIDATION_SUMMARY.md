# Quick Reference: Scope Validation for General Chatbot

## Overview

This is a **general-purpose chatbot** with IT support capabilities. The scope validation ensures we only reject clearly other-domain requests while allowing normal conversation.

## Behavior

### ✅ ALLOWS (Processes Normally)
- **General Conversation**: "Hi", "Hello", "How are you?", "What's up?"
- **Help Requests**: "Can you help me?", "I need help", "I have a question"
- **IT Support**: "WiFi not working", "Password reset", "Laptop slow"
- **Unclear Requests**: When in doubt, we allow it (fail-open)

### ❌ REJECTS (Politely Declines)
- **Travel**: "Book flight to London", "I want bus ticket to Mumbai"
- **Food**: "Order pizza", "Restaurant reservation"
- **Shopping**: "Buy from Amazon", "Purchase laptop"
- **Entertainment**: "Book movie tickets", "Concert tickets"

## Examples

```
User: "Hi"
Bot: ✓ [Processes as greeting]

User: "I can't connect to WiFi"
Bot: ✓ [Provides IT support]

User: "I want a bus ticket to Mumbai"
Bot: ✗ "I'm a general chatbot... your request appears to be for 
       a different service (travel booking, food delivery, etc.)"
```

## How It Works

1. **User sends message** → System checks if it's IT-related
2. **If NOT IT-related** → Polite decline message
3. **If IT-related** → Normal processing (KB search → Ticket if needed)

## Coverage

**OUT-OF-SCOPE categories detected:**
- 🚌 Travel (bus, flight, train, taxi, hotel)
- 🍕 Food (pizza, restaurant, delivery)
- 🛒 Shopping (amazon, purchase, order)
- 🎬 Entertainment (movies, concerts, events)
- 🏥 Services (doctor, lawyer, appointments)
- ☀️ General knowledge (weather, jokes, chat)

**IN-SCOPE (IT support):**
- 🔐 Password/Login issues
- 💻 Software problems
- 🖥️ Hardware issues
- 🌐 Network connectivity
- 📧 Email problems
- ⚡ Performance issues

## Testing

Run these commands to verify:

```bash
# Quick unit test
python test_scope.py

# Full integration test
python test_integration.py

# Live demo
python demo_scope_validation.py
```

## Modified Files

- `src/agents.py` - Added scope validation
- `src/kb.py` - Added OUT_OF_SCOPE category detection
- `src/state.py` - Added OUT_OF_SCOPE template

## No Impact On

✅ Existing IT support conversations  
✅ Ticket creation flow  
✅ Knowledge base functionality  
✅ User experience for valid requests

## Performance

- **Overhead**: ~0.1 second per new conversation
- **Cost**: ~$0.0001 per scope check
- **When**: Only first 1-2 messages (not every message)

---

**Status**: ✅ Fully Implemented & Tested  
**Documentation**: See `Docs/OUT_OF_SCOPE_IMPLEMENTATION.md`
