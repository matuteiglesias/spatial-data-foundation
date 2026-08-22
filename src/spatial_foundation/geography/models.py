from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class GeometryRole(str, Enum):
    ANALYTICAL = "analytical"
    DISPLAY = "display"


class MembershipStatus(str, Enum):
    MATCHED_UNIQUE = "matched_unique"
    UNMATCHED_OUTSIDE = "unmatched_outside"
    AMBIGUOUS_MULTIPLE = "ambiguous_multiple"
    INVALID_POINT = "invalid_point"


class GeographyUnit(FrozenModel):
    geo_uid: str
    provider: str
    version: str
    source_geo_id: str
    country_iso3: str
    native_admin_level: int = Field(ge=0)
    parent_geo_uid: str | None = None
    area_km2: float | None = Field(default=None, ge=0)
    geometry_role: GeometryRole = GeometryRole.ANALYTICAL


def geography_uid(provider: str, version: str, native_admin_level: int, source_geo_id: str) -> str:
    return f"{provider}:{version}:adm{native_admin_level}:{source_geo_id}"
