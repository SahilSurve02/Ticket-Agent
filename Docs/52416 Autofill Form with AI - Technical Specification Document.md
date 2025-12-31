# **Technical Specification: Auto-Fill from Chat**

## **1\. Executive Summary**

This feature introduces intelligent form auto-population capabilities that leverage conversational data from chatbot interactions to streamline form submission workflows. The system will extract structured information from natural language conversations and automatically populate corresponding form fields, reducing manual data entry effort and improving submission accuracy.

**Primary Goals:**

* Reduce form completion time by 60-70% for users who engage with chat first  
* Decrease form submission errors by pre-populating validated data  
* Create seamless transitions between conversational and traditional form interfaces  
* Improve user satisfaction through context-aware assistance

---

## **2\. Problem Statement**

Users currently face friction when transitioning from conversational support channels (chatbot) to structured form submissions. This requires redundant data entry, increases cognitive load, and creates opportunities for data entry errors. The lack of context preservation between chat and form interfaces results in a disjointed user experience.

**Current Pain Points:**

* Users must manually re-enter information already provided in chat conversations  
* No intelligent recognition of user intent or context when switching between interfaces  
* Form validation errors occur due to manual transcription mistakes  
* Support agents lack visibility into the data collection journey  
* Inconsistent experience across different entry points (ITAM, Customer Portal, external pages)

---

## **3\. Proposed Solution**

### **3.1 Overview**

Implement a context-aware auto-fill system that intelligently extracts entities and structured data from chat conversations and automatically populates form fields when users transition to form interfaces. The system will use rule-based logic and natural language processing to identify, validate, and map conversational data to form schemas.

### **3.2 Core Capabilities**

1. **Conversational Data Extraction**: Parse chat messages to identify key entities (names, emails, topics, descriptions, device IDs, etc.)  
2. **Context Preservation**: Maintain session state as users navigate between chat and form interfaces  
3. **Intelligent Field Mapping**: Map extracted entities to appropriate form fields based on context and form schema  
4. **User Control**: Provide clear visibility into auto-filled data with edit capabilities  
5. **Multi-Modal Support**: Enable auto-fill across multiple entry points (Customer Portal, ITAM, Let's Talk, external pages)

---

## **4\. User Stories & Scenarios**

### **4.1 Primary User Stories**

**1\) Chat-to-Form Auto-Fill**  
*As a customer*, I want my conversation with the chatbot to automatically populate the relevant form fields when I switch to the form view, so that I don't have to re-enter information I've already provided.

**Acceptance Criteria:**

* AC1.1: Given the user is accessing the chatbot without having logged in (accessing chatbot through district landing page) and they have provided their name in chat, when they navigate to the form view, the name field is pre-populated with the extracted name. Otherwise, these fields should be pulled from the login account.  
* AC1.2: Given the user is accessing the chatbot without having logged in (accessing chatbot through district landing page) and they have provided contact information (email, phone) in chat, when they open the form, then the contact fields are pre-populated with the correct values. Otherwise, these fields should be pulled from the login account.  
* AC1.3: Given a user has described their issue in a chat conversation, the chatbot suggests a topic based on a lookup of available topics against the described issue. If confirmed by the user, then the topic/category dropdown is pre-selected with the correct topic, and the description field contains an AI-generated summary of the issue from the conversation.  
* AC1.4: Given the user is submitting an IT ticket through the customer portal and they have mentioned a device ID or asset number in chat, when they navigate to the form, then the asset/device field is pre-populated with the correct identifier.  
* AC1.5: Given entity extraction has no information or low confidence (below set threshold; e.g., \<70%) for any field, when the form is displayed, then that field is left empty rather than populated with potentially incorrect data (especially applicable if the used topic form contains custom fields, which should be accounted for in future enhancements).  
* AC1.6: Given multiple pieces of information are extracted from chat, when the form loads, then all applicable fields are populated simultaneously (within a set performance threshold; e.g. 500ms.)  
* AC1.7: Given a user switches to form view, when auto-fill completes, then the user sees a brief, non-intrusive notification indicating fields were pre-filled (e.g., "We've filled in some details from your conversation"). The user may modify the fields before submitting the ticket.

**2\) Form-to-Chat Context Awareness**  
As a *customer*, I want the chatbot to recognize and acknowledge the manual modifications I make to the ticket form when I switch back to chat, so that the conversation remains contextually relevant and doesn't ask for information I've already entered.

**Acceptance Criteria:**

* **AC2.1**: Given a user manually edits one or more fields in the ticket form (e.g., adds phone number "555-0198"), when they switch to the chat tab, then the chatbot acknowledges only the specific fields that were added or changed (e.g., "I see you added your phone number. Great\! What's your name?").

* **AC2.2**: Given a user opens the form first and fills in Topic and partial Description, when they switch to chat for the first time, then the chatbot acknowledges ALL currently filled form content (e.g., "I see you started a Concern about Student Safety. Tell me more?").

* **AC2.3**: Given a user switches from form to chat without making any edits to the form, when the chat loads, then the chatbot does NOT repeat information already visible in the form, but instead focuses on collecting missing required fields (e.g., "Let's complete your request. What's your name and email?").

* **AC2.4**: Given a user has made changes to the form and switches to chat, when the chatbot responds, then the system accurately detects which fields changed since the last interaction (delta detection) and provides context-appropriate responses.

* **AC2.5**: Given a user clears or deletes content from a previously auto-filled field in the form, when they switch to chat, then the chatbot recognizes the field as empty and may ask for that information again if it's a required field.

* **AC2.6**: Given a user manually edits a field that was previously auto-filled from chat, when they switch back to chat, then the system marks that field as "user-modified" and the chatbot does not attempt to re-extract or overwrite it.

* **AC2.7**: Given a form field contains validation errors (e.g., invalid email format), when the user switches to chat, then the chatbot is aware of the validation error and may proactively offer assistance to correct it (e.g., "I noticed the email format looks incorrect. What's your correct email address?").

**3\) Bi-Directional Chat/Form Synchronization**  
As a *customer*, I want the chat and ticket form tabs to stay synchronized as I switch between them so that the chatbot intelligently tracks what I've already provided and only asks for new or missing information without repetition, and my conversation with the chatbot can automatically be reflected in the ticket form in real-time.

**Acceptance Criteria:**

* **AC3.1**: A user may switch between the chat and form tabs at any time. When a switch occurs, data is kept synchronized for a consistent user experience; the user should experience no data loss, duplication, or corruption.

* **AC3.2**: Given the chatbot determines it has collected sufficient information for form submission, when the bot sends a preparation message (e.g., "Let me prepare your request"), then the system automatically switches the user to the form tab second with all collected data populated.

* **AC3.3**: Given a user has a partially completed form and navigates away or closes the browser, when they return to the form, then the system offers to restore their previous session state with all previously entered data intact (within the technically possible timeframe to restore previous session data via cookies or login).

**4\) Admin Configuration**  
*As an administrator*, I want to configure which form fields are eligible for auto-fill and set validation rules, so that I can control data quality, ensure compliance and configure my chatbot behavior.

**TBD \- Custom Form integration plan and Admin Configuration are not detailed** 

### **4.2 Key User Scenarios**

**Scenario A: Chat-Driven Submission**

1. User initiates chat about transportation issue  
2. Bot collects essential field data: topic (Transportation), type (Concern), description, contact details  
3. User switches to form view (manually or bot-triggered if enough information is gathered)  
4. All collected fields are pre-populated  
5. User reviews, adds missing info or makes corrections (if any needed), and submits

**Scenario B: Partial Information Collection**

1. User starts form, fills topic and partial description  
2. User switches to chat for help  
3. Bot acknowledges existing form content (once, on first switch)  
4. User provides additional details in chat  
5. User returns to form; new information is added to existing fields  
6. Bot prompts for missing required fields

**Scenario C: Form-First with Chat Assistance**

1. User opens form directly, enters some information  
2. User gets stuck or needs help  
3. User switches to chat  
4. Bot acknowledges what's already in the form (Rule 1\)  
5. User asks clarifying questions or provides additional context  
6. Bot extracts new information and updates form accordingly

---

## **5\. Functional Requirements**

### **5.1 Data Extraction & Entity Recognition**

**FR-001: Entity Extraction**

* System MAY extract the following information for use in chat conversations and form auto-fill:  
  * Personal identifiers: Name (first, full), email, phone number → MAY also be extracted from Account Login if available  
  * Ticket-specific data: Topic/category, request type (Question/Concern/Complaint/etc.), Issue description, subject  
  * Asset information (for CPortal/ITAM form): Asset ID and Name (associated device details can be looked up by source key)  
  * Location data (TBD–user login, asset location)  
  * Related entities: Ticket IDs, existing request references, previous context

**FR-002: Contextual Extraction Rules**

* System MUST use context from the full conversation thread; as an enhancement, if user is accessing chatbot via login, previous chat information could also be used  
* System MUST recognize and track form field information provided in different messages (e.g., name provided in message 3, email in message 7\)  
* System MUST handle information corrections (e.g., user provides name, then corrects spelling)  
* System MUST distinguish between user-provided and bot-suggested data; fields such as topic should be SUGGESTED for user confirmation before auto-filling

**FR-003: Confidence Scoring**

* System MUST assign confidence scores to extracted entities  
* High-confidence extractions (\>90%): Auto-fill without highlighting  
* Medium-confidence extractions (70-90%): Auto-fill with visual indicator for review (may be introduced as enhancement when custom fields may be auto-filled by chatbot)  
* Low-confidence extractions (\<70%): Do not auto-fill; prompt user for clarification  
* Bot SHOULD ask clarifying questions when confidence is low for a required form field  
* → A way for the user to rate the AI-filled data to improve the feature should be considered (user-rating of AI generated ticket description based on entire conversation context, for example)

### **5.2 Chat-Form Interaction Rules**

**FR-004: Form-First Flow (First Switch to Chat)**

* WHEN user opens form first and then switches to chat for the first time  
* THEN bot SHALL acknowledge ALL form content currently filled  
* Example: "I see you started a Concern about Student Safety regarding bullying. Tell me more?"

**FR-005: User Edited Fields**

* WHEN user manually adds or changes form fields and then switches to chat  
* THEN bot SHALL acknowledge ONLY the specific fields that were added/changed  
* Bot SHALL NOT repeat information that was already acknowledged  
* Example: "I see you added your phone (555-0198). Great\! What's your name?"

**FR-006: User Just Switched (No Edits)** 

* WHEN user switches from form to chat without making any edits  
* THEN bot SHALL NOT repeat information already in the form  
* Bot SHALL focus on completing missing required fields  
* Bot SHALL use forward-moving language ("Let's complete...", "What's your name?")  
* Example: "I can help you finish your request. What's your name and email?"

**FR-007: Switch Session for Different Issues**

* WHEN system detects that the user changes topic mid-conversation  
* THEN system SHALL warn: "Starting a new topic will reset collected info. Continue?"  
* WHEN user confirms topic change  
* THEN system SHALL clear previously collected form data  
* System SHALL maintain conversation history but reset form state

**FR-008: Ambiguous Request Type Handling**

* WHEN system cannot clearly classify request type (Question vs Concern vs Complaint)  
* THEN system SHALL default to "Question"  
* System SHALL allow user to change request type in form or via chat  
* Bot SHALL ask clarifying question: "Is this a Question or Concern?" when confidence is low

### **5.3 Form Behavior & User Interface**

**FR-009: Field Pre-Population**

* System SHALL pre-populate form fields immediately upon user navigating to form view:   
  * Any fields that may be obtained from users login information (if applicable) should be filled  
  * IF a chat conversation was initiated before viewing the ticket form, fields must be autofilled based on the information provided in the chat session  
* Users SHALL be able to edit any pre-populated field  
* Changes to pre-populated fields SHALL persist in session state  
  * Chatbot SHALL acknowledge user modifications to form fields  
  * Chatbot SHALL NOT attempt to overwrite user modifications

**FR-010: Required Field Validation**

* System SHALL prevent submission when required fields are empty  
* System SHALL show inline error messages for missing required fields  
* Chatbot SHALL inquire for missing fields conversationally to guide the user towards ticket completion  
* System SHALL show inline validation errors for invalid formats (email, phone)

**FR-011: Form Preview Before Submission**

* System SHALL display a review screen showing all populated fields before final submission in the **Ticket** tab  
* Review screen SHOULD indicate which fields were auto-filled vs manually entered  
* Users SHALL be able to edit any field from the review screen  
* System SHALL provide a "Submit" action on review screen to submit the form

**FR-012: Form Field Persistence**

* System SHALL maintain form state across chat/form switches within the same session  
* System SHALL persist data for the duration of the user session (until submission or abandonment)  
* System SHALL NOT carry over data to new form instances after successful submission; form data retention SHOULD be contained to a chat session  
* System SHALL end/clear session data after defined period of inactivity (e.g., 24-48 hours)

### **5.4 Knowledge Base Integration**

**FR-013: Knowledge Base Response Handling**

* WHEN user asks question that can be answered from knowledge base  
* AND no answer found after 2 attempts  
* THEN bot SHALL indicate: "I don't have information about \[topic\]. Let me help you submit a ticket to \[team\]"  
* System SHALL pre-fill all collected data  
* IF relevant knowledge base resources are found; system SHALL provide them to the user in the form of a link to relevant articles, FAQ’s, or AI-generated list of quick fixes

**FR-014: Bot Reading Form Content**

* WHEN user switches from form to chat  
* AND bot reads form and mentions form content  
* THEN bot SHALL NOT ask about content already in the form  
* Bot SHALL ask for clarification or additional details only  
* Example: After reading "5th grade robotics" for topic, bot asks for name/email, NOT about robotics again

### **5.5 Duplicate Request Detection**

**FR-015: Similar Open Ticket Detection**

* WHEN system detects similar open ticket for same topic  
* THEN system SHALL prompt: "You have an open ticket about \[topic\] (TKT-12345). Would you like to add to that ticket or create a new one?"  
* User options: "Add to existing" | "Create new"  
* System SHALL link to existing ticket if user selects that option

### **5.6 Multi-Device Support**

**FR-016: Device Selection Logic**

* WHEN user is accessing the chatbot from a platform where they logged in  
* System SHALL detect user’s assigned devices and allow the user to choose which the issue pertains to  
* Otherwise, user may specify the device incurring the issue conversationally

**FR-017: Single Device Auto-Select**

* WHEN user has only one device assigned  
* THEN system SHALL select that device by default; chatbot SHALL acknowledge selection conversationally and ask whether the issue pertains to the users device  
* System SHALL confirm with user before proceeding

**FR-018: Device Not in List**

* WHEN user's device is not in system records  
* THEN system SHALL offer "Other / Not Listed" option or allow for a conversational workaround  
* System SHALL support collecting device information conversationally

### **5.7 Privacy & User Control**

**FR-019: Anonymous User Support**

* WHEN user is accessing the chatbot through an external end-point and wants to submit anonymously  
* THEN system SHALL provide checkbox option to hide name/phone from district view  
* System SHALL clearly communicate privacy implications to user

**FR-020: User Preferences and Admin Controls**

* Admins SHALL be able to disable auto-fill feature   
* Users SHALL be able to clear stored session data at any time  
* \[…\]

### **5.8 Submission Behavior**

**FR-021: Submission Success Flow**

* WHEN form is successfully submitted  
* THEN system SHALL show confirmation message with ticket ID  
* Ticket tab SHALL display an infocard with high-level ticket information  
* Chatbot SHALL acknowledge ticket submission and allow for assisting with new issue rather than ending the chat session directly

**FR-022: Submission Failure Handling**

* WHEN submission fails  
* THEN system SHALL show error message with retry option  
* System SHALL preserve all form data for retry  
* System SHALL offer option to contact support directly  
* System SHALL log error details for administrator review

---

## **6\. Integration Points**

### **6.1 Platform Entry Points**

The auto-fill feature SHALL be implemented across the following entry points (WIP):

1. **Customer Portal**: Primary support ticket submission forms through user portal  
2. **Landing Page:** External-facing forms for public submissions  
3. **ITAM Forms**: IT asset management request forms include an AI check for suggested auto-fill fields (based on context-awareness)  
4. **Tab Navigation**: Forms accessible via tabbed interfaces within the platform

### **6.2 Data Sources**

Auto-fill data shall be sourced from (WIP):

* Chat conversation history (current session)  
* User profile data (name, email, phone, department)  
* User device inventory (for ITAM requests)  
* Previous ticket history (for duplicate detection)  
* IP address and geolocation data (for external forms)  
* Session storage for temporary data persistence (restore previous session within a given time frame)

---

## **7\. Non-Functional Requirements**

### **7.1 Performance**

**TBD**

### **7.2 Scalability**

**TBD** 

### **7.3 Security & Privacy**

**TBD**

### **7.4 Usability**

**TBD**

### **7.5 Maintainability**

**TBD**

---

