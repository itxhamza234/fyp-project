# single_bot.py
#
# WAPDA Voice Call Agent — Pipecat 1.0.0
#
from pipecat.processors.audio.audio_buffer_processor import AudioBufferProcessor
import wave
import asyncio
import os
from typing import Optional
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from context_injectory import build_smart_business_context
from dotenv import load_dotenv
from loguru import logger

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.frames.frames import LLMRunFrame, EndFrame
from pipecat.services.llm_service import FunctionCallParams
from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.runner import PipelineRunner
from pipecat.pipeline.task import PipelineTask, PipelineParams
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.aggregators.llm_response_universal import (
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.services.google.gemini_live.llm import GeminiLiveLLMService
from pipecat.transports.daily.transport import DailyParams, DailyTransport

from tools import (
    file_complaint_tool,
    check_complaint_status_tool,
    request_new_meter_tool,
    get_customer_info_tool,
    escalate_to_human_tool,
)
from db_client import DBClient
from assistant_prompt import build_voice_assistant_prompt
from advisor_prompt import build_voice_advisor_prompt
from daily_recording_worker import fetch_recording_and_store
import aiohttp

load_dotenv(override=True)

logger.remove()
logger.add(lambda msg: print(msg, end=""), level="INFO")


async def send_details_to_flutter(session_id: str, details: dict):
    """Bot collected details ko server store mein save karo — MERGE karta hai"""
    try:
        # Pehle existing data fetch karo
        existing = {}
        async with aiohttp.ClientSession() as sess:
            resp = await sess.get(f"http://localhost:7860/session-details/{session_id}")
            if resp.status == 200:
                body = await resp.json()
                if body.get("found"):
                    existing = body.get("details", {})

        # Merge karo — naye values purane ke upar
        merged = {**existing, **details}

        async with aiohttp.ClientSession() as sess:
            await sess.post(
                f"http://localhost:7860/session-details/{session_id}", json=merged
            )
        logger.info(f"[DETAILS] Merged & stored for session: {session_id}")
    except Exception as e:
        logger.warning(f"[DETAILS] Store failed: {e}")


async def run_voice_pipeline(
    room_url: str,
    token: Optional[str],
    chatbot_id: str,
    chat_id: str,
    session_id: str,
    role: str,
    ai_rules: Optional[str],
    ai_tone: Optional[str],
):
    logger.info(f"[VOICE] Starting WAPDA session {session_id}")
    logger.info(f"[VOICE] Room URL: {room_url}")

    transcript_log = []
    db = DBClient()
    chatbot = await db.get_chatbot_by_id(chatbot_id)
    chatbot_name = chatbot.get("chatbot_name", "WAPDA Helpline")

    def build_system_instruction(role, ai_rules, ai_tone, chatbot_name):
        base = f"""
You are {chatbot_name} - WAPDA Customer Service Representative.

IDENTITY RULES:
- Your name is {chatbot_name}
- If asked your name → say: "Main {chatbot_name} hoon, WAPDA customer service se"
- Never say Gemini, Google, AI, bot, or any model name
- Never reveal backend or AI provider
- You are a HUMAN customer service agent
"""
        DETAILS_COLLECTION_RULES = """
DETAILS COLLECTION RULES (VERY IMPORTANT):

- Jab bhi customer koi field bataye
  (naam, phone, CNIC, area, address, etc.),
  FORAN update_collected_details tool call karo
  us ek field ke saath.

- Agar customer koi correction kare
  (e.g. "naam galat tha, sahi naam X hai"),
  update_collected_details tool call karo
  corrected value ke saath.

- Submit karne se PEHLE
  (file_complaint ya request_new_meter se pehle),
  saari collected details customer ko repeat karo
  aur poocho:

  "Kya yeh details sahi hain?
   Naam: X
   Phone: X
   CNIC: X
   Address: X
   — confirm karein?"

- Sirf customer ki haan sunne ke baad
  final tool call karo.

- Agar customer koi bhi detail galat kahe,
  update_collected_details call karo
  aur phir se confirmation lo.
"""
        if role == "advisor":
            role_prompt = build_voice_advisor_prompt(ai_tone, ai_rules)
        else:
            role_prompt = build_voice_assistant_prompt(ai_tone, ai_rules)
        return base + role_prompt + "\n\n" + DETAILS_COLLECTION_RULES

    system_instruction = build_system_instruction(role, ai_rules, ai_tone, chatbot_name)

    structured_data = await db.get_business_data(chatbot_id)
    _cached_business_data = structured_data or {}
    business_context = build_smart_business_context(structured_data)
    system_instruction = system_instruction + "\n\n" + business_context

    transport = DailyTransport(
        room_url,
        token,
        "WAPDA Voice Agent",
        DailyParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
        ),
    )

    audio_buffer = AudioBufferProcessor(
        sample_rate=16000,
        num_channels=1,
        enable_turn_audio=False
    )

    get_business_schema = FunctionSchema(
        name="get_business_data",
        description="Get WAPDA information like office locations, timings, helpline numbers, billing info",
        properties={
            "category": {
                "type": "string",
                "description": "Category: contact, offices, timings, billing_info, general_info",
            }
        },
        required=["category"],
    )

    file_complaint_schema = FunctionSchema(
        name="file_complaint",
        description="File a new electricity complaint. Call ONLY after collecting ALL details and customer confirmation.",
        properties={
            "name": {"type": "string", "description": "Customer full name"},
            "phone": {"type": "string", "description": "Customer phone number"},
            "cnic": {"type": "string", "description": "CNIC in format XXXXX-XXXXXXX-X"},
            "reference_no": {
                "type": "string",
                "description": "Reference number from electricity bill (optional)",
            },
            "area": {"type": "string", "description": "Area/location name"},
            "address": {"type": "string", "description": "Complete address"},
            "complaint_type": {
                "type": "string",
                "description": "Type: power_outage, low_voltage, billing_issue, faulty_meter, etc",
            },
            "complaint_description": {
                "type": "string",
                "description": "Detailed description of the problem",
            },
        },
        required=[
            "name",
            "phone",
            "cnic",
            "area",
            "address",
            "complaint_type",
            "complaint_description",
        ],
    )

    check_status_schema = FunctionSchema(
        name="check_complaint_status",
        description="Check status of existing complaint or meter request using CNIC and complaint/request number",
        properties={
            "cnic": {"type": "string", "description": "Customer CNIC number"},
            "complaint_no": {
                "type": "string",
                "description": "Complaint number (CMP-XXXXXXXX-XXXXX) or Request number (MTR-XXXXXXXX-XXXXX)",
            },
        },
        required=["cnic", "complaint_no"],
    )

    new_meter_schema = FunctionSchema(
        name="request_new_meter",
        description="Submit new meter connection request. Call ONLY after collecting ALL details and customer confirmation.",
        properties={
            "name": {"type": "string", "description": "Customer full name"},
            "phone": {"type": "string", "description": "Customer phone number"},
            "cnic": {"type": "string", "description": "CNIC in format XXXXX-XXXXXXX-X"},
            "area": {"type": "string", "description": "Area/location name"},
            "address": {"type": "string", "description": "Complete address"},
            "meter_type": {
                "type": "string",
                "description": "single_phase, three_phase, or commercial",
            },
            "premises_type": {
                "type": "string",
                "description": "residential, commercial, or industrial",
            },
        },
        required=[
            "name",
            "phone",
            "cnic",
            "area",
            "address",
            "meter_type",
            "premises_type",
        ],
    )

    get_customer_schema = FunctionSchema(
        name="get_customer_info",
        description="Get all complaints and meter requests for a customer by their CNIC",
        properties={
            "cnic": {"type": "string", "description": "Customer CNIC number"},
        },
        required=["cnic"],
    )

    escalate_schema = FunctionSchema(
        name="escalate_to_human",
        description="Escalate call to human agent. Use for angry customers, complex issues, supervisor requests.",
        properties={
            "reason": {"type": "string", "description": "Reason for escalation"},
            "customer_name": {
                "type": "string",
                "description": "Customer name if known",
            },
            "customer_phone": {
                "type": "string",
                "description": "Customer phone if known",
            },
            "customer_cnic": {
                "type": "string",
                "description": "Customer CNIC if known",
            },
        },
        required=["reason"],
    )

    update_details_schema = FunctionSchema(
        name="update_collected_details",
        description=(
            "Call this EVERY TIME a new piece of customer info is collected or corrected during conversation. "
            "For example: jab customer naam bataye, phone bataye, CNIC bataye, ya koi correction kare. "
            "Do NOT wait for final submission — update field by field as customer speaks."
        ),
        properties={
            "name": {
                "type": "string",
                "description": "Customer full name (if collected)",
            },
            "phone": {"type": "string", "description": "Phone number (if collected)"},
            "cnic": {"type": "string", "description": "CNIC (if collected)"},
            "area": {"type": "string", "description": "Area (if collected)"},
            "address": {"type": "string", "description": "Address (if collected)"},
            "complaint_type": {
                "type": "string",
                "description": "Complaint type (if collected)",
            },
            "reference_no": {
                "type": "string",
                "description": "Reference number (if collected)",
            },
            "meter_type": {
                "type": "string",
                "description": "Meter type (if collected)",
            },
            "premises_type": {
                "type": "string",
                "description": "Premises type (if collected)",
            },
        },
        required=[],
    )

    end_call_schema = FunctionSchema(
        name="end_call",
        description="End the voice call. This is the FINAL action after resolving customer query.",
        properties={
            "reason": {"type": "string", "description": "Reason for ending call"}
        },
        required=[],
    )

    tools = ToolsSchema(
        standard_tools=[
            get_business_schema,
            file_complaint_schema,
            check_status_schema,
            new_meter_schema,
            get_customer_schema,
            escalate_schema,
            end_call_schema,
            update_details_schema,  # ✅ add karo
        ]
    )

    llm = GeminiLiveLLMService(
        api_key=os.getenv("GOOGLE_API_KEY"),
        tools=tools,
        settings=GeminiLiveLLMService.Settings(
            model="models/gemini-2.5-flash-native-audio-preview-09-2025",
            voice="Leda",
            language="en-US",
            system_instruction=system_instruction,
        ),
    )

    # ------------------------------------------------
    # TOOL WRAPPERS
    # ------------------------------------------------

    async def get_business_data_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] get_business_data called | args: {params.arguments}")
        category = params.arguments.get("category")
        data = _cached_business_data.get(category) if _cached_business_data else None

        if not data:
            await params.result_callback(
                "Iss category ki information abhi available nahi hai."
            )
            return

        if isinstance(data, list):
            formatted = []
            for item in data:
                if isinstance(item, dict):
                    formatted.append(" - ".join([f"{k}: {v}" for k, v in item.items()]))
                else:
                    formatted.append(str(item))
            result = "\n".join(formatted)
        elif isinstance(data, dict):
            result = "\n".join([f"{k}: {v}" for k, v in data.items()])
        else:
            result = str(data)

        await params.result_callback(result)

    # ✅ FIXED INDENTATION
    async def file_complaint_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] file_complaint called | args: {params.arguments}")
        try:
            result = await file_complaint_tool(
                chatbot_id=chatbot_id,
                session_id=session_id,
                name=params.arguments.get("name"),
                phone=params.arguments.get("phone"),
                cnic=params.arguments.get("cnic"),
                reference_no=params.arguments.get("reference_no"),
                area=params.arguments.get("area"),
                address=params.arguments.get("address"),
                complaint_type=params.arguments.get("complaint_type"),
                complaint_description=params.arguments.get("complaint_description"),
            )
            logger.info(f"[TOOL] Complaint filed: {result}")

            # ✅ Flutter ko details bhejo
            if result.get("success"):
                asyncio.create_task(
                    send_details_to_flutter(
                        session_id,
                        {
                            **params.arguments,
                            "complaint_no": result.get("complaint_no"),
                            "record_type": "complaint",
                        },
                    )
                )

            await params.result_callback(
                result.get("message", "Complaint filed successfully.")
            )
        except Exception as e:
            logger.error(f"[TOOL] Complaint error: {e}")
            await params.result_callback(
                "Shikayat darj karne mein masla aaya. Please dobara koshish karein.",
            )

    async def check_complaint_status_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] check_complaint_status called | args: {params.arguments}")
        try:
            result = await check_complaint_status_tool(
                cnic=params.arguments.get("cnic"),
                complaint_no=params.arguments.get("complaint_no"),
            )
            await params.result_callback(
                result.get("message", "Status check complete.")
            )
        except Exception as e:
            logger.error(f"[TOOL] Status check error: {e}")
            await params.result_callback(
                "Status check mein masla aaya. Please dobara koshish karein.",
            )

    # ✅ FIXED INDENTATION
    async def request_new_meter_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] request_new_meter called | args: {params.arguments}")
        try:
            result = await request_new_meter_tool(
                chatbot_id=chatbot_id,
                session_id=session_id,
                name=params.arguments.get("name"),
                phone=params.arguments.get("phone"),
                cnic=params.arguments.get("cnic"),
                area=params.arguments.get("area"),
                address=params.arguments.get("address"),
                meter_type=params.arguments.get("meter_type"),
                premises_type=params.arguments.get("premises_type"),
            )
            logger.info(f"[TOOL] Meter request: {result}")

            # ✅ Flutter ko details bhejo
            if result.get("success"):
                asyncio.create_task(
                    send_details_to_flutter(
                        session_id,
                        {
                            **params.arguments,
                            "request_no": result.get("request_no"),
                            "record_type": "meter_request",
                        },
                    )
                )

            await params.result_callback(
                result.get("message", "Meter request submitted successfully."),
            )
        except Exception as e:
            logger.error(f"[TOOL] Meter request error: {e}")
            await params.result_callback(
                "Meter request submit karne mein masla aaya. Please dobara koshish karein.",
            )

    async def get_customer_info_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] get_customer_info called | args: {params.arguments}")
        try:
            result = await get_customer_info_tool(cnic=params.arguments.get("cnic"))
            if not result.get("success"):
                await params.result_callback(
                    result.get("message", "Koi record nahi mila.")
                )
                return

            complaints = result.get("complaints", [])
            meter_requests = result.get("meter_requests", [])

            response_parts = []
            if complaints:
                response_parts.append(
                    f"Total {len(complaints)} shikayatein milti hain:"
                )
                for c in complaints[:5]:
                    response_parts.append(
                        f"- {c.get('complaint_no')}: {c.get('complaint_type')} - Status: {c.get('status')}"
                    )
            if meter_requests:
                response_parts.append(
                    f"Total {len(meter_requests)} meter requests milti hain:"
                )
                for r in meter_requests[:5]:
                    response_parts.append(
                        f"- {r.get('request_no')}: {r.get('meter_type')} - Status: {r.get('status')}"
                    )

            await params.result_callback(
                (
                    "\n".join(response_parts)
                    if response_parts
                    else "Koi record nahi mila."
                ),
            )
        except Exception as e:
            logger.error(f"[TOOL] Customer info error: {e}")
            await params.result_callback(
                "Record dhoondhne mein masla aaya."
            )

    async def escalate_to_human_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] escalate_to_human called | args: {params.arguments}")
        try:
            result = await escalate_to_human_tool(
                session_id=session_id,
                reason=params.arguments.get("reason"),
                customer_name=params.arguments.get("customer_name"),
                customer_phone=params.arguments.get("customer_phone"),
                customer_cnic=params.arguments.get("customer_cnic"),
            )
            logger.info(f"[TOOL] Escalation: {result}")
            await params.result_callback(
                result.get("message", "Call escalated to human agent.")
            )
        except Exception as e:
            logger.error(f"[TOOL] Escalation error: {e}")
            await params.result_callback(
                "Escalation mein masla aaya. Please rukain, human agent jald aa raha hai.",
                
            )

    async def update_collected_details_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] update_collected_details | args: {params.arguments}")
        filtered = {k: v for k, v in params.arguments.items() if v}
        if filtered:
            asyncio.create_task(send_details_to_flutter(session_id, filtered))
        await params.result_callback("Details updated.", )

    async def end_call_wrapper(params: FunctionCallParams):
        logger.info(f"[TOOL] end_call triggered — initiating graceful shutdown")

        await params.result_callback("Call ended.", )

        async def _graceful_shutdown():
            await asyncio.sleep(1.5)
            try:
                logger.info("[DEBUG] Stopping recording")
                await audio_buffer.stop_recording()
                merged = audio_buffer.merge_audio_buffers()
                logger.info(f"[RECORDING] Merged size: {len(merged) if merged else 0}")
                if merged and len(merged) > 0:
                    wav_path = f"/tmp/{session_id}.wav"
                    with wave.open(wav_path, 'wb') as wav_file:
                        wav_file.setnchannels(1)
                        wav_file.setsampwidth(2)
                        wav_file.setframerate(16000)
                        wav_file.writeframes(merged)
                    logger.info(f"[RECORDING] WAV saved: {wav_path}")
                    asyncio.create_task(
                        fetch_recording_and_store(session_id=session_id, wav_path=wav_path)
                    )
                else:
                    logger.warning("[RECORDING] No audio captured")
            except Exception as e:
                logger.error(f"[RECORDING] Save failed: {e}")

            try:
                room_name = room_url.split("/")[-1]
                async with aiohttp.ClientSession() as sess:
                    await sess.post(
                        f"https://api.daily.co/v1/rooms/{room_name}/send-app-message",
                        headers={
                            "Authorization": f"Bearer {os.getenv('DAILY_API_KEY')}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "data": {"type": "call-ended", "action": "end_call"},
                            "recipients": "*",
                        },
                    )
                logger.info("[VOICE] Sent call-ended to frontend via REST")
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.warning(f"[VOICE] send_app_message REST skipped: {e}")

            try:
                await task.queue_frames([EndFrame()])
                logger.info("[VOICE] EndFrame queued — pipeline shutting down")
            except Exception as e:
                logger.error(f"[VOICE] EndFrame queue error: {e}")
                try:
                    await task.cancel()
                except Exception:
                    pass

        asyncio.create_task(_graceful_shutdown())

    # ------------------------------------------------
    # REGISTER TOOLS
    # ------------------------------------------------
    llm.register_function("get_business_data", get_business_data_wrapper)
    llm.register_function("file_complaint", file_complaint_wrapper)
    llm.register_function("check_complaint_status", check_complaint_status_wrapper)
    llm.register_function("request_new_meter", request_new_meter_wrapper)
    llm.register_function("get_customer_info", get_customer_info_wrapper)
    llm.register_function("escalate_to_human", escalate_to_human_wrapper)
    llm.register_function("end_call", end_call_wrapper)
    llm.register_function("update_collected_details", update_collected_details_wrapper)

    context = LLMContext()

    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(),
        ),
    )

    pipeline = Pipeline(
        [
            transport.input(),
            user_aggregator,
            llm,
            assistant_aggregator,
            transport.output(),
            audio_buffer, 
        ]
    )

    task = PipelineTask(
        pipeline,
        params=PipelineParams(
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_first_participant_joined")
    async def on_first_participant_joined(transport, participant):
        logger.info(f"[VOICE] First participant joined — starting conversation")
        await audio_buffer.start_recording()
        logger.info("[DEBUG] Audio recording initialized")
        await asyncio.sleep(1.0)
        await task.queue_frames([LLMRunFrame()])

        @transport.event_handler("on_client_disconnected")
        async def on_client_disconnected(transport, client):
            logger.info(f"[VOICE] Client disconnected - session {session_id}")

            try:
                await db.create_voice_session(
                    chatbot_id=chatbot_id,
                    chat_id=chat_id,
                    session_id=session_id,
                    room_url=room_url,
                    transcript=transcript_log or None,
                )
                
            except Exception as e:
                logger.error(f"Voice session save failed: {e}")

            try:
                await task.cancel()
            except:
                pass
            try:
                await llm.shutdown()
            except:
                pass
            try:
                await transport.leave()
            except:
                pass
    runner = PipelineRunner(handle_sigint=False)

    try:
        await runner.run(task)
    finally:
        try:
            await llm.shutdown()
        except:
            pass