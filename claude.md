# PILOT — Multi-Agent Architecture & Claude Code Blueprint

## Project Overview

PILOT is an Android app that controls any app on the user's phone through voice commands. The user says what they want, and multiple AI agents collaborate to read the screen, plan the task, execute actions, and show progress — all while a glowing border indicates the AI is working.

**Target device:** Samsung Galaxy S25+ (Android 15, One UI 7)
**AI Backend:** FastAPI server on Mac M3 (24GB RAM)
**AI Models:** Groq API (free tier) + local Ollama (backup)
**Build time:** 8 hours at IEEE UBC EDT Competition

---

## Multi-Agent Architecture

PILOT uses 5 specialized agents that communicate through a central **Agent Orchestrator**. Each agent has a single responsibility. They work in a loop: Perceive → Plan → Act → Verify → Report.

```
┌─────────────────────────────────────────────────────────────────┐
│                        USER (Voice Input)                       │
│                  "Order me a pizza from Domino's"                │
└─────────────────────┬───────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENT 0: ORCHESTRATOR                        │
│         Lives on Mac server. Controls the entire flow.          │
│         Routes messages between all other agents.               │
│         Manages conversation state and task progress.           │
└──┬──────────┬───────────┬───────────┬───────────┬──────────────┘
   │          │           │           │           │
   ▼          ▼           ▼           ▼           ▼
┌──────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│AGENT1│ │  AGENT 2  │ │  AGENT 3  │ │  AGENT 4  │ │  AGENT 5  │
│EYES  │ │  PLANNER  │ │  ACTOR   │ │  VERIFIER │ │  VOICE   │
│      │ │           │ │          │ │           │ │          │
│Reads │ │Breaks task│ │Decides   │ │Checks if  │ │Speaks to │
│screen│ │into steps │ │next tap/ │ │step worked│ │user and  │
│on    │ │           │ │type/     │ │or failed  │ │updates   │
│phone │ │           │ │scroll    │ │           │ │glow UI   │
└──────┘ └──────────┘ └──────────┘ └──────────┘ └──────────┘
```

---

## Agent Definitions

### Agent 0: The Orchestrator (Mac Server)

**Role:** Central coordinator. Receives the user's voice request, manages the agent loop, tracks task state, handles errors, and decides when the task is complete.

**Where it runs:** FastAPI server on Mac M3

**What it manages:**
- The current task and its high-level plan (from Agent 2)
- The step the system is currently on
- Conversation history (what actions were taken, what screens were seen)
- Error count and retry logic
- Timeout management (if a step takes too long, abort gracefully)

**State machine:**
```
IDLE → LISTENING → PLANNING → EXECUTING → VERIFYING → EXECUTING → ... → DONE
                                  ↑                        │
                                  └────── (retry) ─────────┘
```

**Orchestrator loop (pseudocode):**
```
1. Receive voice transcription from phone
2. Send to PLANNER (Agent 2) → get back a step-by-step plan
3. For each step in the plan:
   a. Ask EYES (Agent 1) to read the current screen
   b. Send screen state + current step to ACTOR (Agent 3)
   c. ACTOR returns an action (tap/type/scroll)
   d. Phone executes the action
   e. Wait 1-2 seconds for screen to update
   f. Ask EYES (Agent 1) to read the NEW screen
   g. Send old screen + new screen + expected outcome to VERIFIER (Agent 4)
   h. If VERIFIER says success → move to next step
   i. If VERIFIER says failed → retry (max 3 times) or ask user
   j. Update VOICE (Agent 5) with status text for the glow border
4. When all steps done, VOICE (Agent 5) announces completion
```

---

### Agent 1: The Eyes (Phone-Side)

**Role:** Reads the phone screen. Extracts the complete UI element tree via Android Accessibility Service. Optionally captures a screenshot for vision analysis.

**Where it runs:** On the Samsung S25+ as an Android Accessibility Service

**What it does:**
- Traverses the Accessibility node tree from `getRootInActiveWindow()`
- For EVERY element on screen, extracts:
  - `element_id` (generated, sequential)
  - `className` (Button, EditText, TextView, ImageView, etc.)
  - `text` (visible text content)
  - `contentDescription` (accessibility label, especially for icons)
  - `bounds` (screen coordinates: left, top, right, bottom)
  - `isClickable`, `isScrollable`, `isEditable`, `isChecked`
  - `viewIdResourceName` (the developer's XML ID, e.g. "com.uber:id/destination_input")
  - `packageName` (which app is in foreground, e.g. "com.ubercab")
- Builds a structured JSON representation of the screen
- Optionally captures screenshot as JPEG (compressed, ~100KB) for vision fallback

**Output format (sent to server):**
```json
{
  "package": "com.ubercab",
  "activity": "com.ubercab.rider.app.core.root.RootActivity", 
  "screen_title": "Where to?",
  "timestamp": 1711036800,
  "elements": [
    {
      "id": 1,
      "class": "EditText",
      "text": "",
      "hint": "Where to?",
      "content_desc": "Search destination",
      "resource_id": "com.ubercab:id/destination_input",
      "bounds": [24, 180, 456, 240],
      "clickable": true,
      "editable": true,
      "scrollable": false
    },
    {
      "id": 2,
      "class": "TextView",
      "text": "Dr. Patel's Office",
      "content_desc": "Saved place",
      "bounds": [24, 280, 456, 320],
      "clickable": true
    },
    {
      "id": 3,
      "class": "Button",
      "text": "Confirm UberX",
      "bounds": [100, 600, 380, 660],
      "clickable": true
    }
  ],
  "screenshot_b64": "optional, only when server requests it"
}
```

**Key implementation notes:**
- The tree traversal must be recursive (nodes have children)
- Filter out invisible elements (bounds with zero width/height)
- Filter out decorative elements (dividers, spacers with no text/action)
- Cap at ~100 most relevant elements to keep payload small
- The `element_id` is assigned by Agent 1, NOT Android's internal ID — it's just a sequential counter for this screen read. The Actor references these IDs.

---

### Agent 2: The Planner (LLM on Mac)

**Role:** Takes the user's natural language request and breaks it down into a high-level, ordered sequence of steps. Does NOT decide specific UI actions — that's Agent 3's job.

**Where it runs:** Mac server, calls Groq API (llama-3.3-70b-versatile)

**When it's called:** Once per user request, at the very beginning. May be called again if the plan needs to be revised mid-task.

**System prompt:**
```
You are PILOT's Planner. Your job is to break down a user's phone task 
into high-level steps. You do NOT decide specific UI actions like taps 
or types — the Actor agent handles that.

Your steps should be app-aware but action-agnostic. Think about WHAT 
needs to happen, not HOW to tap through the UI.

RULES:
- Each step should be one clear objective
- Include which app should be open for each step
- Include what information is needed (addresses, names, items)
- Include decision points ("if X then Y, else Z")
- Keep plans to 3-8 steps maximum
- The last step is ALWAYS a confirmation/verification step

RESPOND WITH JSON ONLY:
{
  "plan": [
    {"step": 1, "app": "uber", "objective": "Open Uber app", "needs": null},
    {"step": 2, "app": "uber", "objective": "Enter destination address", "needs": "Dr. Patel, 123 Main St"},
    {"step": 3, "app": "uber", "objective": "Select ride type (cheapest)", "needs": null},
    {"step": 4, "app": "uber", "objective": "Confirm and book the ride", "needs": "user confirmation"},
    {"step": 5, "app": "uber", "objective": "Verify ride is booked and get ETA", "needs": null}
  ],
  "info_extracted": {
    "destination": "Dr. Patel, 123 Main St",
    "preferences": "cheapest option"
  }
}
```

**Example inputs → outputs:**

Input: "Order me a pepperoni pizza from Domino's"
```json
{
  "plan": [
    {"step": 1, "app": "doordash", "objective": "Open DoorDash app"},
    {"step": 2, "app": "doordash", "objective": "Search for Domino's restaurant"},
    {"step": 3, "app": "doordash", "objective": "Find and select pepperoni pizza from menu"},
    {"step": 4, "app": "doordash", "objective": "Add to cart with no modifications"},
    {"step": 5, "app": "doordash", "objective": "Go to checkout"},
    {"step": 6, "app": "doordash", "objective": "Review order total and confirm", "needs": "user confirmation for payment"},
    {"step": 7, "app": "doordash", "objective": "Verify order placed and get delivery ETA"}
  ],
  "info_extracted": {
    "restaurant": "Domino's",
    "item": "pepperoni pizza",
    "quantity": 1
  }
}
```

Input: "Send Sarah a message saying I'll be 10 minutes late"
```json
{
  "plan": [
    {"step": 1, "app": "whatsapp", "objective": "Open WhatsApp"},
    {"step": 2, "app": "whatsapp", "objective": "Find Sarah's chat"},
    {"step": 3, "app": "whatsapp", "objective": "Type and send the message"},
    {"step": 4, "app": "whatsapp", "objective": "Verify message was sent"}
  ],
  "info_extracted": {
    "contact": "Sarah",
    "message": "Hey, I'll be about 10 minutes late!"
  }
}
```

---

### Agent 3: The Actor (LLM on Mac)

**Role:** Given the current screen state (from Agent 1) and the current step objective (from Agent 2), decides the SINGLE next UI action to perform.

**Where it runs:** Mac server, calls Groq API (llama-3.3-70b-versatile for text, llama-4-scout for vision fallback)

**When it's called:** Every iteration of the agent loop — after each screen read.

**System prompt:**
```
You are PILOT's Actor. You look at the current phone screen and decide 
the SINGLE next UI action to move toward the current objective.

You receive:
- The current step objective (e.g. "Search for Domino's restaurant")
- The UI element tree (list of all visible elements with IDs)
- Previous actions taken (to avoid loops)

AVAILABLE ACTIONS:
1. {"action": "tap", "element_id": N, "status": "Tapping the search button"}
2. {"action": "type", "element_id": N, "value": "text to type", "status": "Typing the address"}
3. {"action": "scroll_down", "status": "Scrolling down to find more options"}
4. {"action": "scroll_up", "status": "Scrolling up"}
5. {"action": "back", "status": "Going back to previous screen"}
6. {"action": "open_app", "package": "com.ubercab", "status": "Opening Uber"}
7. {"action": "wait", "seconds": 2, "status": "Waiting for page to load"}
8. {"action": "step_done", "status": "This step's objective is complete"}
9. {"action": "need_help", "question": "Which pizza size?", "status": "Need user input"}
10. {"action": "need_vision", "status": "Can't determine action from text tree alone"}

RULES:
- Return EXACTLY ONE action per call
- Always prefer elements with clear text labels over generic ones
- If you see the objective is already achieved on screen, return "step_done"
- If you've done the same action 3 times, try something different
- If element_id doesn't exist in the tree, scroll to find it
- For typing: ALWAYS tap the text field first, then type in a separate action
- If you truly cannot determine what to do, return "need_vision" and the orchestrator will send a screenshot to the vision model
- Keep "status" messages short (5-8 words) — they show on the user's screen

RESPOND WITH JSON ONLY. No other text.
```

**The Actor's decision flow:**
```
1. Read the objective: "Search for Domino's restaurant"
2. Scan UI tree for relevant elements:
   - Is there a search bar? → tap it
   - Is there already text in search? → clear and retype
   - Is search results showing Domino's? → tap it
   - Is there no search visible? → scroll to find it
3. If objective is clearly done (e.g. Domino's page is open) → "step_done"
4. If nothing makes sense → "need_vision" (triggers screenshot + vision model)
```

**Critical: Two-step typing pattern**
The Actor must NEVER try to tap and type in one action. Android's Accessibility API requires:
1. First action: `{"action": "tap", "element_id": 5}` → focuses the text field
2. Second action (next loop iteration): `{"action": "type", "element_id": 5, "value": "Domino's"}` → types the text

The orchestrator must enforce this — if it gets a "type" action, check that the previous action was a "tap" on the same element.

---

### Agent 4: The Verifier (LLM on Mac)

**Role:** After each action is executed, compares the old screen state with the new screen state to determine if the action succeeded, failed, or produced an unexpected result.

**Where it runs:** Mac server, calls Groq API (llama-3.3-70b-versatile)

**When it's called:** After every action execution, once Agent 1 reads the new screen.

**System prompt:**
```
You are PILOT's Verifier. After an action is performed on the phone, 
you compare the BEFORE and AFTER screen states to determine the result.

You receive:
- The action that was just performed
- The screen state BEFORE the action
- The screen state AFTER the action
- The current step objective

RESPOND WITH JSON ONLY:
{"result": "success", "reason": "Search results now show Domino's"}
{"result": "failed", "reason": "Screen didn't change, tap may have missed"}
{"result": "unexpected", "reason": "A dialog appeared asking for location permission", "suggestion": "Dismiss the dialog by tapping Allow"}
{"result": "blocked", "reason": "Login screen appeared, need user credentials"}
```

**Why verification matters:**
- Pop-up dialogs (location permission, notifications, ads) appear unexpectedly
- Actions can fail silently (tap misses the element, keyboard didn't open)
- App crashes or navigation goes to wrong screen
- Loading screens that need a "wait" before next action

**Verifier's decision tree:**
```
1. Are the before/after screens different?
   NO → action likely failed → "failed"
   YES → continue

2. Did the expected thing happen?
   YES → "success" 
   NO → continue

3. Did something unexpected appear?
   Dialog/popup → "unexpected" + suggestion to handle it
   Error message → "failed" + the error text
   Login screen → "blocked" + need user help
   Different screen entirely → "unexpected" + describe what happened

4. Is the screen now closer to the step objective?
   YES → "success" (even if not exactly what we expected)
   NO → "failed"
```

---

### Agent 5: The Voice & Glow (Phone-Side)

**Role:** The user-facing agent. Manages the floating button, voice input/output, and the glowing border overlay. Communicates task progress to the user.

**Where it runs:** On the Samsung S25+ (Jetpack Compose + Overlay Service)

**Components:**

**1. Floating Action Button (always on top)**
- Persistent small circle overlay (using SYSTEM_ALERT_WINDOW)
- User taps it → voice recording starts
- Or responds to wake phrase (stretch goal)
- Shows PILOT icon, subtle pulse when idle

**2. Glow Border Overlay (full screen edge)**
- Draws an animated gradient border around the entire screen
- THREE states with distinct visual identity:
  - **LISTENING** (Blue #00CEFF, slow pulse): "I'm hearing you"
  - **WORKING** (Purple #6C5CE7, flowing animation): "I'm operating the app"
  - **DONE** (Green #00E676, brief flash then fade): "Task complete"
  - **ERROR** (Orange #FF6D00, fast pulse): "Something went wrong"
- Status text bar at bottom of screen showing current action
  - "Opening DoorDash..."
  - "Searching for Domino's..."
  - "Adding pepperoni pizza to cart..."
  - "Order placed! Arriving in 30 minutes."

**3. Voice Output (TTS)**
- Android TextToSpeech for spoken confirmations
- Only speaks at key moments:
  - Start: "Got it, I'll order a pepperoni pizza from Domino's for you."
  - Confirmation needed: "Your order total is $14.99. Should I place it?"
  - Done: "All set! Your pizza will arrive in about 30 minutes."
  - Error: "I'm having trouble with DoorDash. Want me to try again?"

**4. Voice Input (Speech-to-Text)**
- Android SpeechRecognizer
- Activated by floating button tap
- Also listens for "Yes"/"No"/"Stop"/"Cancel" during task execution
- Sends transcription to Orchestrator on Mac server

---

## The Complete Agent Loop (Step by Step)

Here is EXACTLY what happens when a user says "Order me a pepperoni pizza from Domino's":

```
SECOND 0:
  User taps floating button
  Agent 5 (Voice): Glow → BLUE, starts listening
  User speaks: "Order me a pepperoni pizza from Domino's"
  Agent 5 (Voice): Transcribes → sends to Orchestrator

SECOND 1:
  Agent 0 (Orchestrator): Receives "Order me a pepperoni pizza from Domino's"
  Agent 0 → Agent 2 (Planner): "Break this into steps"
  Agent 5 (Voice): TTS says "Got it, ordering a pepperoni pizza from Domino's."
  Agent 5 (Voice): Glow → PURPLE, status: "Planning your order..."

SECOND 2:
  Agent 2 (Planner): Returns 7-step plan
  Agent 0 (Orchestrator): Stores plan, begins Step 1: "Open DoorDash app"
  Agent 5 (Voice): Status: "Opening DoorDash..."

SECOND 3:
  Agent 0 → Agent 3 (Actor): Given objective "Open DoorDash" + current screen (home screen)
  Agent 3 (Actor): Returns {"action": "open_app", "package": "com.doordash.driverapp"}
  Phone executes: launches DoorDash via Intent
  Agent 5 (Voice): Status: "Opening DoorDash..."

SECOND 5 (waited 2s for app to load):
  Agent 0 → Agent 1 (Eyes): "Read the screen"
  Agent 1 (Eyes): Reads DoorDash home screen, returns UI tree
  Agent 0 → Agent 4 (Verifier): Compare before (home screen) vs after (DoorDash)
  Agent 4 (Verifier): {"result": "success", "reason": "DoorDash is now open"}
  Agent 0: Step 1 complete → begin Step 2: "Search for Domino's"

SECOND 6:
  Agent 0 → Agent 3 (Actor): Objective "Search for Domino's" + DoorDash UI tree
  Agent 3 (Actor): Sees search bar (element_id: 4) → {"action": "tap", "element_id": 4}
  Phone executes: taps search bar → keyboard opens
  Agent 5 (Voice): Status: "Searching for Domino's..."

SECOND 8:
  Agent 1 (Eyes): Reads screen (search bar now focused, keyboard visible)
  Agent 0 → Agent 3 (Actor): Same objective, new screen state
  Agent 3 (Actor): Search bar focused → {"action": "type", "element_id": 4, "value": "Domino's"}
  Phone executes: types "Domino's" in search field
  
SECOND 10:
  Agent 1 (Eyes): Reads screen (search results showing)
  Agent 4 (Verifier): {"result": "success", "reason": "Search results show Domino's"}
  Agent 0 → Agent 3 (Actor): Objective still "Search for Domino's"
  Agent 3 (Actor): Sees "Domino's Pizza" in results → {"action": "tap", "element_id": 12}
  Phone executes: taps Domino's listing

SECOND 12:
  Agent 1 (Eyes): Reads Domino's menu page
  Agent 4 (Verifier): {"result": "success", "reason": "Domino's menu is showing"}
  Agent 3 (Actor): {"action": "step_done"}
  Agent 0: Step 2 complete → begin Step 3: "Find pepperoni pizza"
  Agent 5 (Voice): Status: "Finding pepperoni pizza..."

... (continues through remaining steps) ...

SECOND 45:
  Agent 0: Step 6 reached: "Review order and confirm"
  Agent 5 (Voice): TTS says "Your order is $14.99. Shall I place it?"
  Agent 5 (Voice): Glow → BLUE (listening for confirmation)
  User says: "Yes"
  Agent 0: Proceeds to confirm order
  
SECOND 50:
  Agent 3 (Actor): Taps "Place Order" button
  Agent 1 (Eyes): Reads confirmation screen
  Agent 4 (Verifier): {"result": "success", "reason": "Order confirmed, ETA 30 minutes"}
  Agent 5 (Voice): Glow → GREEN flash
  Agent 5 (Voice): TTS says "All set! Your pizza will arrive in about 30 minutes."
  Agent 5 (Voice): Status: "Order placed! Arriving in 30 min."
  Agent 0: Task DONE → return to IDLE
```

---

## Communication Protocol

### Phone ↔ Server Communication

The phone and Mac communicate via HTTP over local WiFi (phone hotspot recommended).

**Phone → Server endpoints:**

```
POST /task/start
  Body: {"transcription": "Order me a pepperoni pizza from Domino's"}
  Response: {"task_id": "abc123", "plan": [...], "confirmation_message": "Got it, ordering..."}

POST /task/screen
  Body: {"task_id": "abc123", "ui_tree": {...}, "screenshot_b64": "optional"}
  Response: {"action": {...}, "status_text": "Searching for Domino's...", "glow_state": "working"}

POST /task/verify
  Body: {"task_id": "abc123", "old_screen": {...}, "new_screen": {...}, "action_performed": {...}}
  Response: {"result": "success|failed|unexpected", "reason": "...", "next_action": {...}}

POST /task/user-response
  Body: {"task_id": "abc123", "response": "yes"}
  Response: {"action": {...}, "status_text": "Placing your order..."}

POST /task/cancel
  Body: {"task_id": "abc123"}
  Response: {"status": "cancelled"}
```

**Simplified flow for hackathon:**

In practice, for the 8-hour hackathon, you can merge some of these into a single endpoint:

```
POST /agent/step
  Body: {
    "task_id": "abc123",
    "user_intent": "Order pepperoni pizza from Domino's",  // original request
    "current_step": "Search for Domino's restaurant",       // from planner
    "ui_tree": {...},                                        // from Eyes
    "screenshot_b64": null,                                  // optional
    "action_history": [...]                                  // last 5 actions
  }
  Response: {
    "action": {"action": "tap", "element_id": 4},
    "status_text": "Tapping the search bar...",
    "glow_state": "working",
    "step_complete": false,
    "task_complete": false
  }
```

This single endpoint does Actor + Verifier logic in one call, reducing latency.

---

## Error Handling Flows

### Pop-up Dialog Detected
```
Agent 1 reads screen → unexpected dialog found (e.g. "Allow location?")
Agent 4 (Verifier): {"result": "unexpected", "suggestion": "Tap Allow"}
Agent 0: Inserts a temporary action to dismiss the dialog
Agent 3: {"action": "tap", "element_id": N} (the Allow button)
Agent 0: Resumes original step
```

### Action Failed (screen didn't change)
```
Attempt 1: Retry the same action
Attempt 2: Try scrolling, then retry
Attempt 3: Request screenshot for vision model analysis
Attempt 4: Ask user "I'm having trouble. Can you help me past this screen?"
```

### App Crashed or Closed
```
Agent 1: Reports package changed (was "com.doordash", now "com.samsung.launcher")
Agent 0: Detects app closure → reopens the app → resumes from last known step
```

### Wrong Screen (navigated somewhere unexpected)
```
Agent 4: {"result": "unexpected", "reason": "We're on the wrong page"}
Agent 0: Sends "back" actions until we reach a known screen
Agent 0: Retries the step from the correct screen
Max 5 back presses before giving up and restarting the app
```

### User Says "Stop" or "Cancel"
```
Agent 5 (Voice): Detects "stop" or "cancel" keyword
Agent 0: Immediately halts all actions
Agent 5: Glow → OFF, TTS says "Stopped. The app is as you left it."
No undo — the user takes over manually from whatever screen they're on
```

---

## Task State Object

The Orchestrator maintains this state throughout a task:

```json
{
  "task_id": "abc123",
  "user_intent": "Order me a pepperoni pizza from Domino's",
  "status": "executing",           // idle | planning | executing | confirming | done | error
  "plan": [
    {"step": 1, "objective": "Open DoorDash", "status": "done"},
    {"step": 2, "objective": "Search Domino's", "status": "done"},
    {"step": 3, "objective": "Find pepperoni pizza", "status": "in_progress"},
    {"step": 4, "objective": "Add to cart", "status": "pending"},
    {"step": 5, "objective": "Checkout", "status": "pending"},
    {"step": 6, "objective": "Confirm order", "status": "pending"},
    {"step": 7, "objective": "Verify placed", "status": "pending"}
  ],
  "current_step_index": 2,
  "info": {
    "restaurant": "Domino's",
    "item": "pepperoni pizza",
    "quantity": 1
  },
  "action_history": [
    {"action": "open_app", "package": "com.doordash", "result": "success"},
    {"action": "tap", "element_id": 4, "result": "success"},
    {"action": "type", "element_id": 4, "value": "Domino's", "result": "success"},
    {"action": "tap", "element_id": 12, "result": "success"}
  ],
  "errors": [],
  "total_actions": 4,
  "start_time": 1711036800,
  "glow_state": "working",
  "status_text": "Finding pepperoni pizza on the menu..."
}
```

---

## Developer Task Assignment (8 Hours)

### Dev 1: Agent 1 (Eyes) + Action Executor
**Owns:** The entire phone-side Accessibility Service

Hours 1-2:
- Android Accessibility Service class
- UI tree reader: recursive traversal of AccessibilityNodeInfo
- JSON serializer for the UI tree
- HTTP client to send tree to Mac server

Hours 3-4:
- Action executor: receives action JSON from server
- Implements: tap (performAction ACTION_CLICK), type (ACTION_SET_TEXT), scroll (dispatchGesture), back (performGlobalAction GLOBAL_ACTION_BACK), open_app (via Intent)
- The core agent loop on phone side: read screen → send to server → get action → execute → repeat

Hours 5-6:
- Handle edge cases: loading screens (wait + retry), dialogs, keyboard management
- Optimize tree reading speed (filter irrelevant nodes early)
- Pre-test all 3 demo app flows

### Dev 2: Agents 2, 3, 4 (Planner + Actor + Verifier)
**Owns:** All LLM logic on the Mac server

Hours 1-2:
- FastAPI server with /agent/step endpoint
- Groq API integration with proper error handling
- Planner agent: system prompt + task decomposition logic
- Test Planner with 3 example tasks

Hours 3-4:
- Actor agent: system prompt + UI tree analysis + action decision
- Verifier agent: before/after comparison logic
- Wire up the full Orchestrator loop: plan → act → verify → repeat
- Handle the simplified single-endpoint flow

Hours 5-6:
- Prompt tuning: make Actor more reliable for Uber, DoorDash, WhatsApp
- Add Ollama fallback if Groq fails
- Add vision fallback path (send screenshot to Groq Llama 4 Scout)
- Error recovery logic: retries, back-navigation, dialog handling

### Dev 3: Agent 5 (Voice & Glow)
**Owns:** Everything the user sees and hears

Hours 1-2:
- Floating overlay button (SYSTEM_ALERT_WINDOW)
- Glow border overlay: custom View with gradient Canvas drawing
- Three glow states: LISTENING (blue), WORKING (purple), DONE (green)
- Basic animation (ValueAnimator for gradient rotation)

Hours 3-4:
- Voice input: SpeechRecognizer integration, transcription
- Voice output: Android TTS for confirmations
- Status text bar at bottom of screen (inside the overlay)
- Real-time status updates from server responses

Hours 5-6:
- Polish animations: smooth state transitions, flowing gradient for WORKING
- "Stop" / "Cancel" voice detection during task execution  
- Confirmation flow: pause and listen for "Yes"/"No" before payments
- Make glow border visible on projector (test contrast/thickness)

### Dev 4: Integration + Demo
**Owns:** Connecting everything together and making the demo flawless

Hours 1-2:
- Jetpack Compose main app: onboarding screen (permission grants), settings
- Network module: Retrofit/Ktor client connecting to Mac server
- Phone hotspot setup, test connectivity Mac ↔ Phone
- All permission handling: Accessibility, Overlay, Microphone

Hours 3-4:
- End-to-end integration: voice → server → action → glow updates
- Test the full loop with a simple app (e.g. open Settings, scroll down)
- Debug communication issues, latency, timeouts
- Build the task state display (for debugging, can be hidden in final app)

Hours 5-6:
- Pre-install and configure demo apps: Uber, DoorDash, WhatsApp
- Create test accounts, pre-fill addresses and contacts
- Run each demo flow 5+ times, note every failure point
- Pre-cache server responses for the 3 demo flows (backup)

Hours 7-8 (ALL devs):
- Demo rehearsal 5+ times
- Record backup video
- Presentation slides (4 max)
- Final permission checks on the S25+

---

## Groq API Model Selection Per Agent

| Agent | Model | Why |
|-------|-------|-----|
| Planner | llama-3.3-70b-versatile | Needs strong reasoning for task decomposition |
| Actor | llama-3.3-70b-versatile | Needs to understand UI trees and decide actions |
| Verifier | llama-3.1-8b-instant | Simpler comparison task, faster response |
| Vision fallback | llama-4-scout-17b-16e-instruct | When text tree isn't enough, send screenshot |
| Backup (all) | qwen3:8b via Ollama (local) | If Groq is down or rate-limited |

---

## What Success Looks Like

At the end of 8 hours, the demo should show:

1. **User taps floating button, says "Book me an Uber to my doctor"**
2. **Screen glows purple.** Status: "Planning your ride..."
3. **Uber opens by itself.** Status: "Opening Uber..."
4. **Address typed into destination.** Status: "Entering destination..."
5. **UberX selected.** Status: "Selecting ride type..."
6. **Voice says: "Your ride will cost $12. Shall I book it?"** Glow → blue
7. **User says "Yes"**
8. **Confirm tapped.** Status: "Booking your ride..."
9. **Glow → green flash.** Voice: "Ride booked. Arriving in 8 minutes."

Total time: under 60 seconds. The audience watches the phone do everything by itself on the projector. The glowing border tells them an AI is in control. They've never seen anything like it.