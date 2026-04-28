# db_client.py
import os
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from loguru import logger

from supabase import create_client, Client

load_dotenv(override=True)


class DBClient:
    def __init__(self):
        # ✅ TUMHARE .env KE MUTABIQ
        self.url = os.getenv("SUPABASE_URL")
        self.key = os.getenv("SUPABASE_SERVICE_KEY")

        if not self.url or not self.key:
            logger.error("[DB] SUPABASE_URL ya SUPABASE_SERVICE_KEY .env mein nahi mila")
            raise ValueError("Missing Supabase credentials in .env")

        self.client: Client = create_client(self.url, self.key)
        logger.info("[DB] Supabase client connected")

    async def _run(self, func, *args, **kwargs):
        """Supabase sync calls ko async mein run karne ke liye wrapper"""
        return await asyncio.to_thread(func, *args, **kwargs)

    # ==================== CHATBOT ====================

    async def get_chatbot_by_id(self, chatbot_id: str):
        try:
            result = await self._run(
                self.client.table("chatbots").select("*").eq("id", chatbot_id).execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[DB] get_chatbot_by_id error: {e}")
            return None

    async def get_chatbot_by_hash(self, hashed_key: str):
        try:
            result = await self._run(
                self.client.table("chatbots").select("*").eq("api_key_hash", hashed_key).execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[DB] get_chatbot_by_hash error: {e}")
            return None

    # ==================== BUSINESS DATA ====================

    async def get_business_data(self, chatbot_id: str):
        try:
            result = await self._run(
                self.client.table("business_data").select("*").eq("chatbot_id", chatbot_id).execute
            )
            if result.data and len(result.data) > 0:
                data = result.data[0]
                data.pop("id", None)
                return data
            return None
        except Exception as e:
            logger.error(f"[DB] get_business_data error: {e}")
            return None

    # ==================== CHAT SESSIONS ====================

    async def get_chat_by_session(self, chatbot_id: str, session_id: str):
        try:
            result = await self._run(
                self.client.table("chats").select("*")
                .eq("chatbot_id", chatbot_id)
                .eq("session_id", session_id)
                .execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[DB] get_chat_by_session error: {e}")
            return None

    async def create_chat_session(self, chatbot_id: str, session_id: str):
        try:
            result = await self._run(
                self.client.table("chats").insert({
                    "chatbot_id": chatbot_id,
                    "session_id": session_id,
                    "created_at": datetime.now().isoformat()
                }).execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]["id"]
            return None
        except Exception as e:
            logger.error(f"[DB] create_chat_session error: {e}")
            return None

    # ==================== COMPLAINTS ====================

    async def create_complaint(self, complaint_data: dict) -> str:
        try:
            result = await self._run(
                self.client.table("complaints").insert(complaint_data).execute
            )
            if result.data and len(result.data) > 0:
                inserted_id = result.data[0]["id"]
                logger.info(f"[DB] Complaint inserted | ID: {inserted_id}")
                return inserted_id
            logger.error("[DB] Complaint insert returned no data")
            return None
        except Exception as e:
            logger.error(f"[DB] create_complaint error: {e}")
            return None

    async def get_complaint_by_no(self, complaint_no: str):
        try:
            result = await self._run(
                self.client.table("complaints").select("*").eq("complaint_no", complaint_no).execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[DB] get_complaint_by_no error: {e}")
            return None

    async def get_complaint_by_cnic_and_no(self, cnic: str, complaint_no: str):
        try:
            result = await self._run(
                self.client.table("complaints").select("*")
                .eq("cnic", cnic)
                .eq("complaint_no", complaint_no)
                .execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[DB] get_complaint_by_cnic_and_no error: {e}")
            return None

    async def get_complaints_by_cnic(self, cnic: str) -> list:
        try:
            result = await self._run(
                self.client.table("complaints").select("*")
                .eq("cnic", cnic)
                .order("created_at", desc=True)
                .limit(20)
                .execute
            )
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[DB] get_complaints_by_cnic error: {e}")
            return []

    # ==================== METER REQUESTS ====================

    async def create_meter_request(self, meter_data: dict) -> str:
        try:
            result = await self._run(
                self.client.table("meter_requests").insert(meter_data).execute
            )
            if result.data and len(result.data) > 0:
                inserted_id = result.data[0]["id"]
                logger.info(f"[DB] Meter request inserted | ID: {inserted_id}")
                return inserted_id
            logger.error("[DB] Meter request insert returned no data")
            return None
        except Exception as e:
            logger.error(f"[DB] create_meter_request error: {e}")
            return None

    async def get_meter_request_by_no(self, request_no: str):
        try:
            result = await self._run(
                self.client.table("meter_requests").select("*").eq("request_no", request_no).execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]
            return None
        except Exception as e:
            logger.error(f"[DB] get_meter_request_by_no error: {e}")
            return None

    async def get_meter_requests_by_cnic(self, cnic: str) -> list:
        try:
            result = await self._run(
                self.client.table("meter_requests").select("*")
                .eq("cnic", cnic)
                .order("created_at", desc=True)
                .limit(20)
                .execute
            )
            return result.data if result.data else []
        except Exception as e:
            logger.error(f"[DB] get_meter_requests_by_cnic error: {e}")
            return []

    # ==================== ESCALATIONS ====================

    async def create_escalation(self, escalation_data: dict) -> str:
        try:
            result = await self._run(
                self.client.table("escalations").insert(escalation_data).execute
            )
            if result.data and len(result.data) > 0:
                inserted_id = result.data[0]["id"]
                logger.info(f"[DB] Escalation inserted | ID: {inserted_id}")
                return inserted_id
            logger.error("[DB] Escalation insert returned no data")
            return None
        except Exception as e:
            logger.error(f"[DB] create_escalation error: {e}")
            return None

    # ==================== VOICE SESSIONS ====================

    async def create_chat_session(self, chatbot_id: str, session_id: str):
        try:
            result = await self._run(
                self.client.table("chats").insert({
                    "chatbot_id": chatbot_id,
                    "session_id": session_id,
                    # ✅ started_at hai tumhare schema mein, created_at nahi
                }).execute
            )
            if result.data and len(result.data) > 0:
                return result.data[0]["id"]
            return None
        except Exception as e:
            logger.error(f"[DB] create_chat_session error: {e}")
            return None