from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, get_db
from app.api.schemas.restaurant_profile import (
    RestaurantProfileCreate,
    RestaurantProfileListResponse,
    RestaurantProfileResponse,
    RestaurantProfileUpdate,
)
from app.infrastructure.db.models import RestaurantProfile

router = APIRouter(prefix="/restaurant-profiles", tags=["restaurant-profiles"])


def _get_profile(db: Session, profile_id: int, org_id: int) -> RestaurantProfile:
    profile = db.query(RestaurantProfile).filter(
        RestaurantProfile.id == profile_id,
        RestaurantProfile.org_id == org_id,
    ).first()
    if not profile:
        raise HTTPException(status_code=404, detail="Restaurant profile not found.")
    return profile


@router.get("", response_model=RestaurantProfileListResponse)
def list_profiles(
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestaurantProfileListResponse:
    profiles = db.query(RestaurantProfile).filter(
        RestaurantProfile.org_id == current["org_id"]
    ).order_by(RestaurantProfile.created_at).all()
    return RestaurantProfileListResponse(profiles=profiles)


@router.post("", response_model=RestaurantProfileResponse, status_code=status.HTTP_201_CREATED)
def create_profile(
    body: RestaurantProfileCreate,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestaurantProfileResponse:
    profile = RestaurantProfile(org_id=current["org_id"], **body.model_dump())
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.get("/{profile_id}", response_model=RestaurantProfileResponse)
def get_profile(
    profile_id: int,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestaurantProfileResponse:
    return _get_profile(db, profile_id, current["org_id"])


@router.patch("/{profile_id}", response_model=RestaurantProfileResponse)
def update_profile(
    profile_id: int,
    body: RestaurantProfileUpdate,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RestaurantProfileResponse:
    profile = _get_profile(db, profile_id, current["org_id"])
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(profile, field, value)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.delete("/{profile_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_profile(
    profile_id: int,
    current: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    profile = _get_profile(db, profile_id, current["org_id"])
    db.delete(profile)
    db.commit()
