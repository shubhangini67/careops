from pydantic import BaseModel, EmailStr


class RegisterRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    org_name: str


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserMe(BaseModel):
    id: int
    email: str
    full_name: str | None
    org_id: int
    org_name: str
    org_slug: str
    role: str
