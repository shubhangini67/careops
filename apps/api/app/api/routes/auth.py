import re

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.api.schemas.auth import LoginRequest, RegisterRequest, TokenResponse, UserMe
from app.core.auth import create_access_token, hash_password, verify_password
from app.infrastructure.db.models import Organization, User, UserOrganization, UserRole

router = APIRouter(prefix="/auth", tags=["auth"])


def _slugify(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    return slug.strip("-")


def _ensure_unique_slug(db: Session, base: str) -> str:
    slug = base
    counter = 1
    while db.query(Organization).filter(Organization.slug == slug).first():
        slug = f"{base}-{counter}"
        counter += 1
    return slug


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> TokenResponse:
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="Email already registered.")

    slug = _ensure_unique_slug(db, _slugify(body.org_name))
    org = Organization(name=body.org_name, slug=slug)
    db.add(org)
    db.flush()

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        full_name=body.full_name,
    )
    db.add(user)
    db.flush()

    membership = UserOrganization(user_id=user.id, org_id=org.id, role=UserRole.owner)
    db.add(membership)
    db.commit()
    db.refresh(user)

    token = create_access_token({"sub": str(user.id), "org_id": str(org.id), "role": UserRole.owner.value})
    return TokenResponse(access_token=token)


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.query(User).filter(User.email == body.email).first()
    if not user or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is inactive.")

    membership = db.query(UserOrganization).filter(UserOrganization.user_id == user.id).first()
    if not membership:
        raise HTTPException(status_code=400, detail="User has no organisation.")

    token = create_access_token({
        "sub": str(user.id),
        "org_id": str(membership.org_id),
        "role": membership.role.value,
    })
    return TokenResponse(access_token=token)


@router.get("/me", response_model=UserMe)
def me(
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserMe:
    user = db.query(User).filter(User.id == current["user_id"]).first()
    org = db.query(Organization).filter(Organization.id == current["org_id"]).first()
    membership = db.query(UserOrganization).filter(
        UserOrganization.user_id == current["user_id"],
        UserOrganization.org_id == current["org_id"],
    ).first()

    if not user or not org or not membership:
        raise HTTPException(status_code=404, detail="User or organisation not found.")

    return UserMe(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        org_id=org.id,
        org_name=org.name,
        org_slug=org.slug,
        role=membership.role.value,
    )
