"""Voice-input transcription for the planning modal's free-text intake.

Reuses the Groq credential already configured for GroqProvider (app/infrastructure/llm/groq.py)
-- Groq's SDK exposes Whisper transcription (client.audio.transcriptions.create) alongside its
chat completions API on the same key, so this needs no new provider/signup. Kept as a standalone
function rather than a BaseLLMProvider method: transcription isn't part of the complete/
complete_json contract those providers share, and routing it through get_llm()'s
FallbackLLMProvider wrapper would be the wrong shape for a single-provider capability.

Unlike the enrichers (which fail open to None so one bad signal never blocks a plan), this raises
on failure -- it's a direct user action (they clicked record and are waiting), so the caller
should surface a retryable error rather than silently losing what was said.
"""

import asyncio

from groq import Groq

from app.core.settings import get_settings

_TRANSCRIPTION_MODEL = "whisper-large-v3"


async def transcribe(audio_bytes: bytes, filename: str) -> str:
    """Transcribe recorded audio to text via Groq's Whisper endpoint."""
    api_key = get_settings().groq_api_key
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in environment variables.")

    client = Groq(api_key=api_key)
    result = await asyncio.to_thread(
        client.audio.transcriptions.create,
        file=(filename, audio_bytes),
        model=_TRANSCRIPTION_MODEL,
    )
    return result.text
