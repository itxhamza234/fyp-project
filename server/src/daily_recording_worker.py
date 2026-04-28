import asyncio
import httpx
import os
from db_client import DBClient
from supabase import create_client
from dotenv import load_dotenv
# from pydub import AudioSegment
load_dotenv()
DAILY_API_KEY = os.getenv("DAILY_API_KEY")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
# from imageio_ffmpeg import get_ffmpeg_exe
# from pydub import AudioSegment
import ffmpeg
from imageio_ffmpeg import get_ffmpeg_exe
# ffmpeg_path = get_ffmpeg_exe()
FFMPEG_PATH = get_ffmpeg_exe()
# AudioSegment.converter = ffmpeg_path
# AudioSegment.ffprobe = ffmpeg_path.replace("ffmpeg", "ffprobe")

async def fetch_recording_and_store(session_id, room_url):

    db = DBClient()

    headers = {
        "Authorization": f"Bearer {DAILY_API_KEY}"
    }

    for _ in range(24):  # retry ~1 minute

        async with httpx.AsyncClient() as client:

            room_name = room_url.split("/")[-1]

            r = await client.get(
                f"https://api.daily.co/v1/recordings?room_name={room_name}",
                headers=headers
            )
            recordings = r.json().get("data", [])

            for rec in recordings:

                room_name = room_url.split("/")[-1]

                if rec["room_name"] == room_name:

                    if rec["status"] != "finished":
                        continue

                    recording_id = rec["id"]

                    link_resp = await client.get(
                        f"https://api.daily.co/v1/recordings/{recording_id}/access-link",
                        headers=headers
                    )

                    recording_url = link_resp.json()["download_link"]

                    audio = await client.get(recording_url)
                    ext = "mp4"
                    video_path = f"/tmp/{session_id}.{ext}"

                    with open(video_path, "wb") as f:
                        f.write(audio.content)

                    # convert mp4/webm → mp3
                    # audio_file = AudioSegment.from_file(video_path)

                    mp3_path = f"/tmp/{session_id}.mp3"

                    (
                        ffmpeg
                        .input(video_path)
                        .output(mp3_path, acodec='libmp3lame', audio_bitrate='128k')
                        .run(cmd=FFMPEG_PATH)
                    )

                    # audio_file.export(mp3_path, format="mp3")

                    storage_path = f"{session_id}.mp3"

                    try:
                        with open(mp3_path, "rb") as f:

                            result = supabase.storage.from_("recordings").upload(
                                path=storage_path,
                                file=f,
                                file_options={"content-type": "audio/mpeg"}
                            )

                        print("Upload success", result)

                    except Exception as e:
                        print(f"Supabase upload failed: {e}")

                    participants = rec.get("participants_count", 0)

                    await db.update_voice_recording(
                        session_id=session_id,
                        recording_path=storage_path,
                        duration=rec["duration"],
                        participants=participants
                    )
                    print("Recording saved")

                    return

        await asyncio.sleep(5)

    print("Recording not found")