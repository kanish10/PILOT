# PILOT — Mac M3 Server Setup Guide

## Do ALL of this Friday night (March 20). Not Saturday morning.

The Mac M3 runs the AI brain for PILOT. It receives screen data from the phone, decides what action to take, and sends instructions back. This guide gets everything installed, tested, and ready so Saturday morning you just type `./start.sh` and you're live.

---

## Step 1: Get API Keys (10 minutes)

### Groq (Primary AI — FREE)

1. Go to https://console.groq.com
2. Sign up with Google (no credit card needed)
3. Click **API Keys** in the left sidebar
4. Click **Create API Key**
5. Name it "PILOT-hackathon"
6. Copy the key (starts with `gsk_...`)
7. Save it somewhere safe — you cannot see it again

**Test it works:**
```bash
curl -s https://api.groq.com/openai/v1/chat/completions \
  -H "Authorization: Bearer gsk_YOUR_KEY_HERE" \
  -H "Content-Type: application/json" \
  -d '{"model":"llama-3.3-70b-versatile","messages":[{"role":"user","content":"Say hello in 5 words"}],"max_tokens":20}' | python3 -m json.tool
```

You should see a JSON response with "choices" containing a greeting. If you see an error, your key is wrong.

### Groq Vision Model — Verify Access

```bash
# Test that you can access the vision model too
curl -s https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer gsk_YOUR_KEY_HERE" | python3 -c "
import sys, json
models = json.load(sys.stdin)['data']
vision = [m['id'] for m in models if 'scout' in m['id'] or 'vision' in m['id'].lower()]
print('Vision models available:', vision if vision else 'NONE — check Groq console for current vision models')
text = [m['id'] for m in models if '70b' in m['id']]
print('70B text models:', text[:3])
"
```

Note whatever vision model name appears — you'll use it in the server config.

---

## Step 2: Install Ollama (5 minutes)

Ollama is the backup AI that runs locally if Groq goes down.

```bash
# Install Ollama
brew install ollama

# Start the Ollama service
ollama serve &

# Wait 5 seconds for it to start
sleep 5

# Pull the backup text model (fast, handles UI trees)
ollama pull qwen3:8b

# Verify it works
curl -s http://localhost:11434/api/generate \
  -d '{"model":"qwen3:8b","prompt":"Say hello in 5 words","stream":false}' | python3 -c "
import sys, json
print(json.load(sys.stdin)['response'])
"
```

You should see a short greeting. If Ollama isn't running, the curl will fail with "connection refused" — just run `ollama serve &` again.

---

## Step 3: Install Python Dependencies (2 minutes)

```bash
# Create a project directory
mkdir -p ~/pilot-server
cd ~/pilot-server

# Install dependencies
pip3 install fastapi uvicorn httpx python-multipart --break-system-packages

# Verify
python3 -c "import fastapi, uvicorn, httpx; print('All dependencies installed')"
```

---

## Step 4: Create the Server (copy-paste this entire file)

```bash
cd ~/pilot-server
```

Create the main server file:

```bash
cat > server.py << 'SERVEREOF'
"""
PILOT Server — Multi-Agent Orchestrator
Runs on Mac M3. Phone sends screen data, server returns actions.
"""

import os
import re
import json
import time
import asyncio
from typing import Optional
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

# ============================================================
# CONFIG
# ============================================================

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
OLLAMA_URL = "http://localhost:11434/api/generate"

# Models — update these if Groq changes their model names
GROQ_TEXT_MODEL = "llama-3.3-70b-versatile"        # fast text reasoning
GROQ_FAST_MODEL = "llama-3.1-8b-instant"           # ultra-fast for verification
GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"  # vision fallback
OLLAMA_BACKUP_MODEL = "qwen3:8b"                    # offline backup

app = FastAPI(title="PILOT Server")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ============================================================
# DATA MODELS
# ============================================================

class StartTaskRequest(BaseModel):
    transcription: str  # what the user said

class StepRequest(BaseModel):
    task_id: str
    user_intent: str
    current_step: str
    ui_tree: str                        # JSON string of screen elements
    screenshot_b64: Optional[str] = None
    action_history: list = []

class VerifyRequest(BaseModel):
    task_id: str
    action_performed: dict
    old_screen_summary: str
    new_screen_summary: str
    current_step: str

class UserResponseRequest(BaseModel):
    task_id: str
    response: str  # "yes", "no", "stop", or freeform

# In-memory task storage (fine for hackathon)
tasks = {}

# ============================================================
# LLM CALLING UTILITIES
# ============================================================

async def call_groq_text(system: str, user: str, model: str = None, max_tokens: int = 300) -> Optional[str]:
    """Call Groq text API. Returns response text or None on failure."""
    if not GROQ_KEY:
        return None
    model = model or GROQ_TEXT_MODEL
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ],
                    "temperature": 0.1,
                    "max_tokens": max_tokens
                })
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"Groq error {resp.status_code}: {resp.text[:200]}")
                return None
    except Exception as e:
        print(f"Groq call failed: {e}")
        return None


async def call_groq_vision(system: str, user_text: str, image_b64: str) -> Optional[str]:
    """Call Groq vision API with screenshot. Returns response text or None."""
    if not GROQ_KEY:
        return None
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(GROQ_URL,
                headers={"Authorization": f"Bearer {GROQ_KEY}", "Content-Type": "application/json"},
                json={
                    "model": GROQ_VISION_MODEL,
                    "messages": [
                        {"role": "system", "content": system},
                        {"role": "user", "content": [
                            {"type": "text", "text": user_text},
                            {"type": "image_url", "image_url": {
                                "url": f"data:image/jpeg;base64,{image_b64}"
                            }}
                        ]}
                    ],
                    "temperature": 0.1,
                    "max_tokens": 300
                })
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"Groq vision error {resp.status_code}: {resp.text[:200]}")
                return None
    except Exception as e:
        print(f"Groq vision failed: {e}")
        return None


async def call_ollama(prompt: str) -> Optional[str]:
    """Call local Ollama as backup. Returns response text or None."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(OLLAMA_URL, json={
                "model": OLLAMA_BACKUP_MODEL,
                "prompt": prompt,
                "stream": False
            })
            if resp.status_code == 200:
                return resp.json().get("response", "")
            return None
    except Exception as e:
        print(f"Ollama failed: {e}")
        return None


def extract_json(text: str) -> Optional[dict]:
    """Extract first JSON object from LLM response text."""
    if not text:
        return None
    # Try to find a JSON block
    patterns = [
        r'```json\s*(.*?)\s*```',  # markdown code block
        r'```\s*(.*?)\s*```',       # generic code block
        r'(\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\})',  # nested JSON
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                continue
    # Last resort: try the whole text
    try:
        return json.loads(text.strip())
    except:
        return None


# ============================================================
# AGENT 2: PLANNER
# ============================================================

PLANNER_SYSTEM = """You are PILOT's Planner agent. Break down the user's phone task into sequential steps.

RULES:
- Each step has one clear objective
- Include which app to use
- Keep to 3-8 steps maximum
- Last step is always verification
- Extract key info (names, addresses, items) from the request

RESPOND WITH JSON ONLY:
{
  "plan": [
    {"step": 1, "app": "app_name", "objective": "What to accomplish"},
    {"step": 2, "app": "app_name", "objective": "Next thing to do"}
  ],
  "info": {"key": "extracted information from user request"},
  "confirmation": "Short sentence confirming what you'll do"
}"""


# ============================================================
# AGENT 3: ACTOR
# ============================================================

ACTOR_SYSTEM = """You are PILOT's Actor agent. Given the current screen UI elements and an objective, decide the SINGLE next action.

AVAILABLE ACTIONS (respond with exactly one):
{"action": "tap", "element_id": N, "status": "Short description"}
{"action": "type", "element_id": N, "value": "text to type", "status": "Short description"}
{"action": "scroll_down", "status": "Scrolling to find more"}
{"action": "scroll_up", "status": "Scrolling up"}
{"action": "back", "status": "Going back"}
{"action": "open_app", "package": "com.example.app", "status": "Opening app"}
{"action": "wait", "seconds": 2, "status": "Waiting for load"}
{"action": "step_done", "status": "Objective achieved"}
{"action": "need_help", "question": "What should I choose?", "status": "Need user input"}
{"action": "need_vision", "status": "Cannot determine from text alone"}

RULES:
- Return EXACTLY ONE JSON action, nothing else
- To type text: first tap the field (one action), then type (next action). Never tap+type together
- If objective is clearly complete on screen, return step_done
- If same action was tried 3+ times in history, try something different
- Keep status to 5-8 words — it shows on the user's screen
- Common packages: com.ubercab (Uber), com.dd.doordash (DoorDash), com.whatsapp (WhatsApp)"""


# ============================================================
# AGENT 4: VERIFIER
# ============================================================

VERIFIER_SYSTEM = """You are PILOT's Verifier agent. Compare the screen before and after an action to check if it worked.

RESPOND WITH JSON ONLY:
{"result": "success", "reason": "Brief explanation"}
{"result": "failed", "reason": "Why it failed"}
{"result": "unexpected", "reason": "What happened instead", "suggestion": "How to handle it"}
{"result": "blocked", "reason": "Why we can't continue"}"""


# ============================================================
# ENDPOINTS
# ============================================================

@app.get("/health")
async def health():
    """Check server status and API connectivity."""
    groq_ok = False
    ollama_ok = False

    # Test Groq
    if GROQ_KEY:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get("https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {GROQ_KEY}"})
                groq_ok = resp.status_code == 200
        except:
            pass

    # Test Ollama
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            resp = await client.get("http://localhost:11434/api/tags")
            ollama_ok = resp.status_code == 200
    except:
        pass

    return {
        "status": "ok",
        "groq_connected": groq_ok,
        "groq_key_set": bool(GROQ_KEY),
        "ollama_connected": ollama_ok,
        "models": {
            "text": GROQ_TEXT_MODEL,
            "vision": GROQ_VISION_MODEL,
            "fast": GROQ_FAST_MODEL,
            "backup": OLLAMA_BACKUP_MODEL
        }
    }


@app.post("/task/start")
async def start_task(req: StartTaskRequest):
    """User said something. Plan the task."""
    task_id = f"task_{int(time.time())}"

    # Call Planner
    result = await call_groq_text(PLANNER_SYSTEM, f"USER SAID: {req.transcription}")

    # Fallback to Ollama if Groq failed
    if not result:
        result = await call_ollama(f"{PLANNER_SYSTEM}\n\nUSER SAID: {req.transcription}")

    plan_data = extract_json(result)

    if not plan_data or "plan" not in plan_data:
        return {
            "task_id": task_id,
            "error": "Could not create a plan",
            "raw_response": result
        }

    # Store task state
    tasks[task_id] = {
        "task_id": task_id,
        "user_intent": req.transcription,
        "plan": plan_data["plan"],
        "info": plan_data.get("info", {}),
        "current_step_index": 0,
        "action_history": [],
        "status": "executing",
        "start_time": time.time()
    }

    return {
        "task_id": task_id,
        "plan": plan_data["plan"],
        "total_steps": len(plan_data["plan"]),
        "confirmation": plan_data.get("confirmation", "Working on it..."),
        "first_step": plan_data["plan"][0]["objective"],
        "glow_state": "working"
    }


@app.post("/task/step")
async def execute_step(req: StepRequest):
    """Given current screen, decide next action."""

    # Build the Actor prompt
    user_msg = f"""OBJECTIVE: {req.current_step}

USER'S ORIGINAL REQUEST: {req.user_intent}

CURRENT SCREEN UI ELEMENTS:
{req.ui_tree}

RECENT ACTION HISTORY:
{json.dumps(req.action_history[-5:], indent=2) if req.action_history else "No actions yet"}"""

    # Try Groq text first (fast path)
    result = await call_groq_text(ACTOR_SYSTEM, user_msg)
    action = extract_json(result) if result else None

    # If Actor says it needs vision, and we have a screenshot
    if action and action.get("action") == "need_vision" and req.screenshot_b64:
        result = await call_groq_vision(ACTOR_SYSTEM, user_msg, req.screenshot_b64)
        action = extract_json(result) if result else None

    # If Groq failed entirely, try Ollama
    if not action:
        result = await call_ollama(f"{ACTOR_SYSTEM}\n\n{user_msg}")
        action = extract_json(result) if result else None

    # If everything failed
    if not action:
        return {
            "action": "wait",
            "seconds": 2,
            "status": "Thinking...",
            "glow_state": "working",
            "step_complete": False,
            "task_complete": False,
            "raw_response": result
        }

    # Check if this step is done
    step_complete = action.get("action") == "step_done"
    task_complete = False

    if step_complete and req.task_id in tasks:
        task = tasks[req.task_id]
        task["current_step_index"] += 1
        if task["current_step_index"] >= len(task["plan"]):
            task_complete = True
            task["status"] = "done"

    # Determine glow state
    glow = "done" if task_complete else "confirming" if action.get("action") == "need_help" else "working"

    return {
        **action,
        "glow_state": glow,
        "step_complete": step_complete,
        "task_complete": task_complete,
        "status": action.get("status", "Working...")
    }


@app.post("/task/verify")
async def verify_step(req: VerifyRequest):
    """Check if the last action worked."""

    user_msg = f"""ACTION PERFORMED: {json.dumps(req.action_performed)}
CURRENT STEP OBJECTIVE: {req.current_step}

SCREEN BEFORE ACTION:
{req.old_screen_summary}

SCREEN AFTER ACTION:
{req.new_screen_summary}"""

    # Use fast model for verification
    result = await call_groq_text(VERIFIER_SYSTEM, user_msg, model=GROQ_FAST_MODEL, max_tokens=150)
    verification = extract_json(result) if result else None

    if not verification:
        # If verification fails, assume success and keep going
        return {"result": "success", "reason": "Verification skipped"}

    return verification


@app.post("/task/user-response")
async def user_response(req: UserResponseRequest):
    """User responded to a question (yes/no/stop/freeform)."""
    if req.task_id in tasks:
        task = tasks[req.task_id]

        if req.response.lower() in ["stop", "cancel"]:
            task["status"] = "cancelled"
            return {"action": "cancelled", "status": "Task cancelled", "glow_state": "off"}

        if req.response.lower() in ["yes", "yeah", "yep", "sure", "go ahead", "do it"]:
            return {"action": "continue", "status": "Proceeding...", "glow_state": "working"}

        if req.response.lower() in ["no", "nah", "nope", "don't", "cancel that"]:
            task["status"] = "cancelled"
            return {"action": "cancelled", "status": "Cancelled", "glow_state": "off"}

        # Freeform response — add to context for next Actor call
        task["action_history"].append({"user_said": req.response})
        return {"action": "continue", "status": "Got it...", "glow_state": "working"}

    return {"action": "error", "status": "Task not found"}


@app.post("/task/cancel")
async def cancel_task(req: UserResponseRequest):
    """Cancel a running task."""
    if req.task_id in tasks:
        tasks[req.task_id]["status"] = "cancelled"
    return {"status": "cancelled", "glow_state": "off"}


@app.get("/task/{task_id}")
async def get_task(task_id: str):
    """Get current task state (for debugging)."""
    if task_id in tasks:
        return tasks[task_id]
    return {"error": "Task not found"}


# ============================================================
# STARTUP
# ============================================================

if __name__ == "__main__":
    if not GROQ_KEY:
        print("\n⚠️  WARNING: GROQ_API_KEY not set!")
        print("   Run: export GROQ_API_KEY=gsk_your_key_here\n")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
SERVEREOF

echo "✅ server.py created"
```

---

## Step 5: Create the Startup Script

```bash
cd ~/pilot-server

cat > start.sh << 'STARTEOF'
#!/bin/bash
echo "🚀 Starting PILOT Server..."
echo ""

# Check for API key
if [ -z "$GROQ_API_KEY" ]; then
    echo "⚠️  GROQ_API_KEY not set!"
    echo "   Run: export GROQ_API_KEY=gsk_your_key_here"
    echo "   Then run this script again."
    exit 1
fi

# Start Ollama in background (if not running)
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "Starting Ollama..."
    ollama serve &
    sleep 3
fi

# Get Mac's IP address
MAC_IP=$(ifconfig | grep "inet " | grep -v 127.0.0.1 | head -1 | awk '{print $2}')

echo "============================================"
echo "  PILOT Server"
echo "============================================"
echo ""
echo "  Server URL:  http://${MAC_IP}:8000"
echo "  Health:      http://${MAC_IP}:8000/health"
echo "  Docs:        http://${MAC_IP}:8000/docs"
echo ""
echo "  📱 Phone should connect to: http://${MAC_IP}:8000"
echo ""
echo "  Groq API:    ✅ Key set"
echo "  Ollama:      $(curl -s http://localhost:11434/api/tags > /dev/null 2>&1 && echo '✅ Running' || echo '❌ Not running')"
echo ""
echo "============================================"
echo ""

# Start the server
python3 -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
STARTEOF

chmod +x start.sh
echo "✅ start.sh created"
```

---

## Step 6: Create the Environment File

```bash
cd ~/pilot-server

cat > .env << 'ENVEOF'
# Paste your actual Groq key here
GROQ_API_KEY=gsk_paste_your_real_key_here
ENVEOF

echo "✅ .env created — NOW EDIT IT with your real Groq key:"
echo "   nano ~/pilot-server/.env"
```

Edit the .env file and paste your real Groq API key.

Then add this to your shell:
```bash
echo 'export $(cat ~/pilot-server/.env | xargs)' >> ~/.zshrc
source ~/.zshrc
```

---

## Step 7: Test Everything (5 minutes)

### Start the server:
```bash
cd ~/pilot-server
./start.sh
```

### In a NEW terminal tab, run these tests:

**Test 1 — Health check:**
```bash
curl -s http://localhost:8000/health | python3 -m json.tool
```
Expected: `groq_connected: true`, `ollama_connected: true`

**Test 2 — Plan a task:**
```bash
curl -s -X POST http://localhost:8000/task/start \
  -H "Content-Type: application/json" \
  -d '{"transcription": "Order me a pepperoni pizza from Dominos"}' | python3 -m json.tool
```
Expected: a JSON response with a multi-step plan

**Test 3 — Actor decides an action:**
```bash
curl -s -X POST http://localhost:8000/task/step \
  -H "Content-Type: application/json" \
  -d '{
    "task_id": "test",
    "user_intent": "Order pepperoni pizza from Dominos",
    "current_step": "Open DoorDash app",
    "ui_tree": "{\"package\": \"com.samsung.launcher\", \"elements\": [{\"id\": 1, \"class\": \"AppIcon\", \"text\": \"DoorDash\", \"clickable\": true, \"bounds\": [100,200,200,300]}, {\"id\": 2, \"class\": \"AppIcon\", \"text\": \"WhatsApp\", \"clickable\": true}]}",
    "action_history": []
  }' | python3 -m json.tool
```
Expected: an action like `{"action": "tap", "element_id": 1, ...}` or `{"action": "open_app", ...}`

**Test 4 — Verify Ollama backup works:**
```bash
curl -s -X POST http://localhost:11434/api/generate \
  -d '{"model":"qwen3:8b","prompt":"Say hello in exactly 5 words","stream":false}' | python3 -c "
import sys, json
print('Ollama response:', json.load(sys.stdin)['response'][:100])
"
```

---

## Step 8: Network Setup for Phone Connection

### Option A: Phone Hotspot (RECOMMENDED)

This is the most reliable option — no campus WiFi firewall issues.

1. On the Samsung S25+: **Settings > Connections > Mobile Hotspot > Turn ON**
2. On the Mac: Connect to the phone's WiFi hotspot
3. The Mac gets an IP like `172.20.10.X` — note this IP
4. The phone connects to `http://172.20.10.X:8000`

### Option B: Same WiFi Network

If both devices are on the same WiFi:
1. Find Mac's IP: run `ifconfig | grep "inet " | grep -v 127.0.0.1`
2. The phone connects to `http://YOUR_MAC_IP:8000`
3. Test from the phone's browser: open `http://YOUR_MAC_IP:8000/health`

If the phone can't reach the server, the WiFi network is blocking local traffic. Switch to Option A.

---

## Step 9: Saturday Morning Checklist

```
[ ] Mac is charged and plugged in
[ ] Open terminal and run:
      cd ~/pilot-server && ./start.sh
[ ] Health check shows both groq and ollama connected
[ ] Phone is connected (hotspot or same WiFi)
[ ] Phone can reach http://MAC_IP:8000/health in browser
[ ] Tell the Android devs the server IP address
```

---

## What the Server Does During the Hackathon

The Android devs will call these endpoints from the phone:

```
POST /task/start       → Phone sends voice transcription, gets back a plan
POST /task/step        → Phone sends current screen UI tree, gets back next action  
POST /task/verify      → Phone sends before/after screens, gets back success/fail
POST /task/user-response → Phone sends user's yes/no response
GET  /task/{id}        → Debug: see full task state
GET  /health           → Verify server is alive
GET  /docs             → Interactive API docs (Swagger UI)
```

The server logs every request to the terminal, so you can see what's happening in real-time. If something goes wrong during the demo, the terminal shows exactly which LLM call failed and why.

---

## Troubleshooting

### "Groq returned 429 (rate limited)"
You hit the free tier limit. Wait 1 minute — limits reset per-minute.
If persistent: the server auto-falls back to Ollama. Tasks will be slower (~3s instead of ~1s) but still work.

### "Ollama connection refused"
Ollama isn't running. In a new terminal: `ollama serve &`

### "Phone can't reach server"
1. Check Mac firewall: **System Settings > Network > Firewall > OFF** (or add exception for port 8000)
2. Try phone hotspot instead of WiFi
3. Verify IP: `ifconfig | grep "inet " | grep -v 127.0.0.1`

### "LLM returns garbage instead of JSON"
The prompts might need tuning for specific apps. During the hackathon, Dev 2 can iterate on the system prompts in server.py. The `--reload` flag on uvicorn means changes take effect instantly — no restart needed.

### "Server crashed"
Just run `./start.sh` again. All task state is in-memory so it resets, but that's fine during a hackathon.

---

## File Structure When Done

```
~/pilot-server/
├── server.py          # The main server (all 5 agents)
├── start.sh           # One-command startup script
├── .env               # Your Groq API key
└── (that's it — keep it simple)
```

Total setup time: ~30 minutes including testing.
Total cost: $0.