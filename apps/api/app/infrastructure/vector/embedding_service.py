from google import genai
from google.genai import types


class EmbeddingService:
    """Converts text to vector embeddings using Gemini embedding model."""

    def __init__(self):
        from app.core.settings import get_settings

        api_key = get_settings().gemini_api_key
        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")
        self.client = genai.Client(api_key=api_key)
        self.model = "models/gemini-embedding-001"

    def embed(self, text: str) -> list[float]:
        """Convert a single text string to a vector embedding."""
        response = self.client.models.embed_content(
            model=self.model,
            contents=types.Content(
                parts=[types.Part(text=text)],
                role="user"
            )
        )
        return response.embeddings[0].values

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Convert a list of texts to vector embeddings."""
        return [self.embed(text) for text in texts]