import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from app.models import FileStatus


class FileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    status: FileStatus
    crs: str | None
    feature_count: int | None
    error: str | None
    created_at: datetime


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    feature_index: int
    geometry_type: str | None
    measurement_crs: str | None
    area_m2: float | None
    length_m: float | None
    reason: str | None
    properties: dict

    @computed_field
    def area_ha(self) -> float | None:
        return None if self.area_m2 is None else self.area_m2 / 10_000

    @computed_field
    def length_km(self) -> float | None:
        return None if self.length_m is None else self.length_m / 1_000


class MeasurementPage(BaseModel):
    file_id: uuid.UUID
    source_crs: str | None
    total: int
    limit: int
    offset: int
    items: list[MeasurementOut]
