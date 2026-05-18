import asyncio
import os
import ffmpeg
from imageio_ffmpeg import get_ffmpeg_exe
from db_client import DBClient
from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
FFMPEG_PATH = get_ffmpeg_exe()


async def fetch_recording_and_store(session_id: str, wav_path: str):
    """WAV → MP3 → Supabase Storage"""

    db = DBClient()

    # WAV file exist karta hai?
    if not os.path.exists(wav_path):
        print(f"[RECORDING] WAV not found: {wav_path}")
        return

    # MP3 mein convert karo
    mp3_path = f"/tmp/{session_id}.mp3"
    try:
        (
            ffmpeg
            .input(wav_path)
            .output(mp3_path, acodec='libmp3lame', audio_bitrate='128k')
            .run(cmd=FFMPEG_PATH, overwrite_output=True)
        )
        print(f"[RECORDING] Converted to MP3: {mp3_path}")
    except Exception as e:
        print(f"[RECORDING] FFmpeg error: {e}")
        return

    # Supabase mein upload karo
    storage_path = f"{session_id}.mp3"
    try:
        with open(mp3_path, "rb") as f:
            result = supabase.storage.from_("recordings").upload(
                path=storage_path,
                file=f,
                file_options={"content-type": "audio/mpeg"}
            )
        print(f"[RECORDING] Uploaded to Supabase: {storage_path}")
    except Exception as e:
        print(f"[RECORDING] Supabase upload failed: {e}")
        return

    # DB mein path save karo
    await db.update_voice_recording(
        session_id=session_id,
        recording_path=storage_path,
        duration=0,
        participants=0
    )

    # Temp files cleanup
    try:
        os.remove(wav_path)
        os.remove(mp3_path)
    except:
        pass

    print(f"[RECORDING] ✅ Done for session {session_id}")