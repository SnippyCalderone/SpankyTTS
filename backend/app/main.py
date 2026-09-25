import logging
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from openai import OpenAI
from pydantic import BaseModel

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

SERVICE_NAME = "spanky-tts-backend"
MODEL_NAME = "gpt-4o-mini-tts"
DEFAULT_VOICE = "cedar"
DEFAULT_INSTRUCTIONS = (
    "Read naturally as a professional audiobook narrator. "
    "Use natural pacing and expressive but restrained delivery."
)
MAX_TEXT_CHARS = 5000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("spanky_tts_backend")

app = FastAPI(title=SERVICE_NAME)


class TTSRequest(BaseModel):
    text: str
    voice: str = DEFAULT_VOICE
    instructions: str = DEFAULT_INSTRUCTIONS


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": SERVICE_NAME}


@app.post("/tts")
def tts(payload: TTSRequest) -> Response:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="'text' is required and must not be blank")

    if len(text) > MAX_TEXT_CHARS:
        raise HTTPException(
            status_code=413,
            detail=f"'text' exceeds maximum size of {MAX_TEXT_CHARS} characters",
        )

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="OPENAI_API_KEY is not configured on the backend",
        )

    voice = payload.voice.strip() if payload.voice else DEFAULT_VOICE
    instructions = payload.instructions.strip() if payload.instructions else DEFAULT_INSTRUCTIONS

    logger.info("TTS request: chars=%s voice=%s", len(text), voice)
    start = time.perf_counter()

    try:
        client = OpenAI(api_key=api_key)
        with client.audio.speech.with_streaming_response.create(
            model=MODEL_NAME,
            voice=voice,
            input=text,
            instructions=instructions,
            response_format="pcm",
        ) as speech_response:
            audio_bytes = speech_response.read()

    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - start) * 1000)
        logger.exception("TTS generation failed after %sms", elapsed_ms)
        raise HTTPException(status_code=502, detail="OpenAI TTS request failed") from exc

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info("TTS success: bytes=%s elapsed_ms=%s", len(audio_bytes), elapsed_ms)

    return Response(
        content=audio_bytes,
        media_type="application/octet-stream",
        headers={
            "X-Audio-Sample-Rate": "24000",
            "X-Audio-Encoding": "pcm_s16le",
            "X-Audio-Channels": "1",
        },
    )
