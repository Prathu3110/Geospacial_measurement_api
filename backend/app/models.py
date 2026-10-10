import enum
import uuid
from datetime import datetime

from geoalchemy2 import Geometry
from sqlalchemy import ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class FileStatus(enum.StrEnum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class UploadedFile(Base):
    __tablename__ = "uploaded_files"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    filename: Mapped[str]
    # Stored as plain text, not a Postgres ENUM, so adding a status needs no type migration.
    status: Mapped[FileStatus] = mapped_column(String(20), default=FileStatus.PENDING)
    crs: Mapped[str | None]
    feature_count: Mapped[int | None]
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    features: Mapped[list["Feature"]] = relationship(
        back_populates="file", cascade="all, delete-orphan", order_by="Feature.feature_index"
    )


class Feature(Base):
    __tablename__ = "features"

    id: Mapped[int] = mapped_column(primary_key=True)
    file_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("uploaded_files.id", ondelete="CASCADE"), index=True
    )
    feature_index: Mapped[int]
    geometry_type: Mapped[str | None]
    # Always WGS84, so the map and PostGIS queries need no per-file CRS logic.
    geometry = mapped_column(Geometry(srid=4326, spatial_index=False), nullable=True)
    properties: Mapped[dict] = mapped_column(JSONB, default=dict)
    measurement_crs: Mapped[str | None]
    area_m2: Mapped[float | None]
    length_m: Mapped[float | None]
    reason: Mapped[str | None]

    file: Mapped[UploadedFile] = relationship(back_populates="features")
