#
# Copyright (c) 2025, Daily
#
# SPDX-License-Identifier: BSD 2-Clause License
#
import asyncio
import os
from contextlib import asynccontextmanager
from typing import Any, Dict, List
from single_bot import run_voice_pipeline
import aiohttp
import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pipecat.transports.daily.utils import DailyRESTHelper, DailyRoomParams
from uuid import uuid4

# Load environment variables
load_dotenv(override=True)

from db_client import DBClient
from single_bot import run_voice_pipeline
import time

# ✅ Session details store — bot ki collected details yahan save hongi
session_details_store = {}


class VoiceSessionManager:
    def __init__(self):
        self.sessions: Dict[str, asyncio.Task] = {}

    async def create_session(self, room_url: str, token: str):
        session_id = str(uuid4())
        task = asyncio.create_task(
            run_voice_pipeline(room_url, token, session_id)
        )
        self.sessions[session_id] = task
        return session_id

    async def remove_session(self, session_id: str):
        task = self.sessions.get(session_id)
        if task:
            task.cancel()
            del self.sessions[session_id]


@asynccontextmanager
async def lifespan(app: FastAPI):
    aiohttp_session = aiohttp.ClientSession()
    app.state.aiohttp_session = aiohttp_session

    app.state.daily_rest_helper = DailyRESTHelper(
        daily_api_key=os.getenv("DAILY_API_KEY", ""),
        daily_api_url=os.getenv("DAILY_API_URL", "https://api.daily.co/v1"),
        aiohttp_session=aiohttp_session,
    )

    yield

    await aiohttp_session.close()


# Initialize FastAPI app with lifespan manager
app = FastAPI(lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─────────────────────────────────────────────
# MAIN CONNECT ENDPOINT
# ─────────────────────────────────────────────
@app.post("/connect")
async def bot_connect(request: Request):

    body = await request.json()
    data = body.get("requestData", body)

    chatbot_id = data.get("chatbot_id")
    session_id = data.get("session_id")

    if not chatbot_id:
        raise HTTPException(status_code=400, detail="Missing chatbot_id")

    if not session_id:
        raise HTTPException(status_code=400, detail="Missing session_id")

    db = DBClient()

    # Validate chatbot by ID
    chatbot = await db.get_chatbot_by_id(chatbot_id)
    if not chatbot:
        raise HTTPException(status_code=403, detail="Invalid chatbot_id")

    # Allocate Daily room
    daily_rest_helper = request.app.state.daily_rest_helper

    room = await daily_rest_helper.create_room(
        DailyRoomParams(
            properties={
                "enable_recording": "cloud",
                "exp": int(time.time()) + 900
            }
        )
    )

    if not room.url:
        raise HTTPException(status_code=500, detail="Room creation failed")

    user_token = await daily_rest_helper.get_token(room.url)
    bot_token = await daily_rest_helper.get_token(room.url)

    room_data = {
        "room_url": room.url,
        "user_token": user_token,
        "session_id": session_id,
        "bot_token": bot_token
    }

    # Create chat session
    chat = await db.get_chat_by_session(chatbot_id, session_id)
    if chat:
        chat_id = chat["id"]
    else:
        chat_id = await db.create_chat_session(chatbot_id, session_id)

    # Start voice pipeline
    asyncio.create_task(
        run_voice_pipeline(
            room_url=room_data["room_url"],
            token=room_data["bot_token"],
            chatbot_id=chatbot_id,
            chat_id=chat_id,
            session_id=session_id,
            role=chatbot.get("role", "advisor"),
            ai_rules=chatbot.get("ai_rules"),
            ai_tone=chatbot.get("ai_tone"),
        )
    )

    return {
        "room_url": room_data["room_url"],
        "token": room_data["user_token"],
        "session_id": session_id,
    }


# ─────────────────────────────────────────────
# ✅ SESSION DETAILS ENDPOINTS
# Flutter in yahan se details fetch karega
# ─────────────────────────────────────────────

@app.post("/session-details/{session_id}")
async def store_details(session_id: str, request: Request):
    """single_bot.py yahan details save karega jab tool call ho"""
    body = await request.json()
    session_details_store[session_id] = body
    return {"ok": True}


@app.get("/session-details/{session_id}")
async def get_details(session_id: str):
    """Flutter har 3 sec mein yahan se details fetch karega"""
    data = session_details_store.get(session_id)
    if not data:
        return {"found": False}
    return {"found": True, "details": data}


@app.delete("/session-details/{session_id}")
async def clear_details(session_id: str):
    """Call khatam hone par cleanup"""
    session_details_store.pop(session_id, None)
    return {"ok": True}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=7860)