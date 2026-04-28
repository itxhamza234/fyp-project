# 🎙️ Instant Voice AI Chatbot (Real-Time Multi-Tenant System)

A **real-time, production-grade voice chatbot system** built using FastAPI, Daily (WebRTC), and Gemini Live LLM.

This system enables users to **talk directly with an AI agent via voice**, while handling:

* Live conversation
* Business-aware responses
* Lead capture
* Session recording & storage

---

# 🚀 Overview

This is an **enterprise voice pipeline system** where:

1. User joins a WebRTC room
2. Speaks naturally (no button needed)
3. AI processes speech in real-time
4. Responds with voice
5. Entire session is recorded & stored

---

# 🧠 Core Architecture

### 🔹 Client (Frontend)

* Built with Vite + JavaScript
* Connects via WebRTC (Daily)
* Sends/receives real-time audio

### 🔹 Server (Backend)

* FastAPI-based
* Handles session creation
* Runs voice pipeline
* Manages database + recordings

---

# ⚙️ Tech Stack

| Layer            | Technology         |
| ---------------- | ------------------ |
| Backend          | FastAPI            |
| Voice Transport  | Daily WebRTC       |
| LLM              | Google Gemini Live |
| VAD              | Silero VAD         |
| Database         | Supabase           |
| Storage          | Supabase Storage   |
| Audio Processing | FFmpeg             |
| Pipeline Engine  | Pipecat            |

---

# 📁 Project Structure

```id="p1q2w3"
instant-voice/
│
├── client/
│   └── javascript/
│       ├── src/
│       ├── index.html
│       └── vite.config.js
│
├── server/
│   ├── src/
│   │   ├── server.py              # FastAPI entry
│   │   ├── single_bot.py          # Voice pipeline (core)
│   │   ├── db_client.py           # Supabase integration
│   │   ├── daily_recording_worker.py  # Recording fetch + upload
│   │   ├── assistant_prompt.py
│   │   ├── advisor_prompt.py
│   │   ├── context_injectory.py
│   │   ├── tools.py
│   │
│   ├── .env
│   ├── bot-example.py
│   ├── pyproject.toml
│
└── README.md
```

---

# 🔄 How It Works (Real Flow)

### 1. Client Connects

* Sends `chatbot_id` + `session_id`

### 2. Server (`/connect`)

* Validates chatbot via DB 
* Creates Daily room
* Generates tokens
* Starts voice pipeline 

---

### 3. Voice Pipeline (`single_bot.py`)

* Uses:

  * DailyTransport (audio stream)
  * Gemini Live LLM
  * Silero VAD (speech detection)
* Injects:

  * Business context 
  * Role-based prompts (assistant/advisor)

---

### 4. AI Capabilities

#### 🧠 Smart Context Injection

* Dynamically injects business data
* Falls back to core data if large

#### 🛠 Tool Calling

* Fetch business info
* Store leads automatically 

---

### 5. Conversation Handling

* Real-time speech → AI → speech
* Transcript captured live

---

### 6. Recording System

* Daily cloud recording starts automatically
* Worker fetches + converts + uploads 

Flow:

* Video → MP4
* Convert → MP3
* Upload → Supabase

---

### 7. Session Storage

* Chat session saved
* Transcript stored
* Recording linked

---

# ⚡ Client-Side Improvement (IMPORTANT)

Using:

👉 `DailyTransport.bufferLocalAudioUntilBotReady = enabled`

### 🔥 Result:

* User can start speaking **within ~1 second**
* No need to wait for full connection
* Audio buffered until bot ready

💥 Improves UX significantly (instant feel)

---

# 🧠 AI Behavior System

### 🎭 Roles Supported

#### Assistant Mode

* Friendly support
* FAQ handling
* Lead capture

#### Advisor Mode

* Strategic guidance
* Decision framing
* Controlled escalation

---

### 📞 Lead Capture (Automatic)

System detects:

* Name
* Email
* Phone

And stores via tool call.

---

# ▶️ Setup Instructions (WSL Recommended)

## 1. Clone Project

```bash id="cmd1"
git clone <repo>
cd instant-voice
```

---

## 2. Backend Setup

```bash id="cmd2"
cd server
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Environment Variables

Create `.env`:

```env id="env2"
DAILY_API_KEY=
DAILY_API_URL=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
GOOGLE_API_KEY=
```

---

## 4. Run Server

```bash id="cmd3"
python src/server.py
```

---

## 5. Client Setup

```bash id="cmd4"
cd client/javascript
npm install
npm run dev
```

---

# 🌐 API Endpoint

### Connect

```
POST /connect
```

**Body:**

```json id="json1"
{
  "chatbot_id": "uuid",
  "session_id": "session_123"
}
```

**Response:**

```json id="json2"
{
  "room_url": "...",
  "token": "..."
}
```

---

# 🔐 Security

* Chatbot validated via DB
* No direct API exposure
* Session isolated
* Multi-tenant safe

---

# 🚀 Key Features

✅ Real-time voice AI
✅ WebRTC-based communication
✅ Multi-tenant architecture
✅ Business-aware responses
✅ Lead capture system
✅ Automatic recording + storage
✅ Tool-based LLM integration

---

# ⚠️ Important Notes

* Requires WSL (Linux environment recommended)
* FFmpeg required for audio conversion
* Supabase must be configured
* Daily API required

---

# 🚀 Future Improvements

* Streaming transcripts UI
* Multi-language voice
* Voice cloning
* Analytics dashboard
* Queue-based scaling

---

# 👨‍💻 Final Note

This is a **production-level voice AI system**, not a demo.

* Real-time processing
* Enterprise pipeline
* Scalable architecture

💥 Built for SaaS / AI automation platforms
