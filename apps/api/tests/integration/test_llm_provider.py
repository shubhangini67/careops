import pytest
import asyncio
import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# 1. Calculate path to project root
# Path(__file__).resolve() is tests/integration/test_llm_provider.py
# .parent is tests/integration/
# .parent.parent is tests/
# .parent.parent.parent is the project root (where .env and app/ live)
BASE_DIR = Path(__file__).resolve().parent.parent.parent
ENV_PATH = BASE_DIR / ".env"

# 2. Load env variables using the absolute path to the root .env
load_dotenv(dotenv_path=ENV_PATH)

# 3. Insert project root into sys.path to allow 'from app...' imports
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.infrastructure.llm.gemini import GeminiProvider


@pytest.mark.asyncio
async def test_gemini_complete():
    """Test basic text completion via actual API call."""
    provider = GeminiProvider()
    response = await provider.complete(
        prompt="In one sentence, what is a pizza?",
        system_prompt="You are a helpful assistant."
    )
    print(f"\nGemini response: {response}")
    assert response is not None
    assert len(response) > 0


@pytest.mark.asyncio
async def test_gemini_complete_json():
    """Test JSON completion via actual API call."""
    provider = GeminiProvider()
    response = await provider.complete_json(
        prompt="Give me a recommendation to reduce food waste in a restaurant.",
        system_prompt="You are a restaurant operations manager."
    )
    print(f"\nJSON response: {response}")
    assert isinstance(response, dict)
    # Ensure the dictionary contains data
    assert len(response) > 0