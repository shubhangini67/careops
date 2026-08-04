from google import genai
from google.genai import types
import json

from app.infrastructure.llm.base import BaseLLMProvider


class GeminiProvider(BaseLLMProvider):
    """Gemini LLM provider using the google-genai SDK."""

    def __init__(self) -> None:
        super().__init__()
        from app.core.settings import get_settings

        api_key = get_settings().gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set in environment variables.")
        self.client = genai.Client(api_key=api_key)
        self.provider_name = "gemini"
        self.model = "gemini-2.5-flash"

    async def complete(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> str:
        """Send a prompt to Gemini and return text response."""
        contents = []

        if system_prompt:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=f"{system_prompt}\n\n{prompt}")]
                )
            )
        else:
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part(text=prompt)]
                )
            )

        config = types.GenerateContentConfig(temperature=temperature) if temperature is not None else None

        response = self.client.models.generate_content(
            model=self.model,
            contents=contents,
            config=config,
        )

        usage = response.usage_metadata
        if usage:
            self.record_usage(
                model=self.model,
                prompt_tokens=usage.prompt_token_count or 0,
                completion_tokens=usage.candidates_token_count or 0,
            )
            self._trace_generation(
                prompt=prompt,
                system_prompt=system_prompt,
                output_text=response.text,
                prompt_tokens=usage.prompt_token_count or 0,
                completion_tokens=usage.candidates_token_count or 0,
            )

        return response.text

    async def complete_json(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> dict:
        """Send a prompt to Gemini and return parsed JSON response."""
        json_system = "You must respond with valid JSON only. No explanation, no markdown, no backticks."
        combined_system = f"{json_system}\n{system_prompt}" if system_prompt else json_system

        raw = await self.complete(prompt, system_prompt=combined_system, temperature=temperature)

        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        clean = clean.strip()

        return json.loads(clean)
