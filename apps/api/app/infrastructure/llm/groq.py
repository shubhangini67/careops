import json

from app.infrastructure.llm.base import BaseLLMProvider


class GroqProvider(BaseLLMProvider):
    """
    Groq LLM provider using the groq SDK.
    Free tier — much higher rate limits than Gemini free tier.

    Get your key at: https://console.groq.com
    Set GROQ_API_KEY in your .env file.
    """

    def __init__(self) -> None:
        super().__init__()
        from groq import Groq
        from app.core.settings import get_settings

        api_key = get_settings().groq_api_key
        if not api_key:
            raise ValueError("GROQ_API_KEY is not set in environment variables.")

        self.client = Groq(api_key=api_key)
        self.provider_name = "groq"
        self.model = "llama-3.3-70b-versatile"  # best free model on Groq for reasoning

    async def complete(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> str:
        """Send a prompt to Groq and return text response."""
        messages = []

        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        kwargs = {"temperature": temperature} if temperature is not None else {}
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            **kwargs,
        )

        output_text = response.choices[0].message.content

        if response.usage:
            self.record_usage(
                model=self.model,
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
            )
            self._trace_generation(
                prompt=prompt,
                system_prompt=system_prompt,
                output_text=output_text,
                prompt_tokens=response.usage.prompt_tokens or 0,
                completion_tokens=response.usage.completion_tokens or 0,
            )

        return output_text

    async def complete_json(
        self, prompt: str, system_prompt: str | None = None, temperature: float | None = None,
    ) -> dict:
        """Send a prompt to Groq and return parsed JSON response."""
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
