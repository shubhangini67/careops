from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.api.schemas.settings import OrgSettings, OrgSettingsResponse
from app.infrastructure.db.models import Organization

router = APIRouter(prefix="/settings", tags=["settings"])

_DEFAULTS = OrgSettings().model_dump()


def _require_owner(current: dict) -> None:
    if current.get("role") != "owner":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="Only workspace owners can manage settings.")


def _get_org(db: Session, org_id: int) -> Organization:
    org = db.query(Organization).filter(Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found.")
    return org


@router.get("", response_model=OrgSettingsResponse)
def get_settings(
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgSettingsResponse:
    org = _get_org(db, current["org_id"])
    merged = {**_DEFAULTS, **(org.settings or {})}
    return OrgSettingsResponse(
        org_id=org.id,
        org_name=org.name,
        settings=OrgSettings(**merged),
    )


@router.patch("", response_model=OrgSettingsResponse)
def update_settings(
    body: OrgSettings,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrgSettingsResponse:
    _require_owner(current)
    org = _get_org(db, current["org_id"])

    existing = org.settings or {}
    updated  = {**existing, **body.model_dump()}
    org.settings = updated
    db.add(org)
    db.commit()
    db.refresh(org)

    return OrgSettingsResponse(
        org_id=org.id,
        org_name=org.name,
        settings=OrgSettings(**org.settings),
    )
