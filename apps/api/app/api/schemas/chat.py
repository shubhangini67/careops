from typing import Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1000)
    history: list[ChatMessage] = []
    session_id: Optional[int] = None  # None -> start a new persisted session


class ChatSessionSummary(BaseModel):
    id: int
    title: Optional[str]
    message_count: int
    updated_at: str


class ChatSessionDetail(BaseModel):
    id: int
    title: Optional[str]
    messages: list[ChatMessage]
