import json
import os
import tempfile
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_session
from app.models import Feature, FileStatus, UploadedFile
from app.schemas import FileOut, MeasurementOut, MeasurementPage
from app.services.processing import process_file

router = APIRouter(prefix="/api/files", tags=["files"])

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
ALLOWED_SUFFIXES = {".kml", ".zip"}

SessionDep = Annotated[Session, Depends(get_session)]


@router.post("/", response_model=FileOut, status_code=status.HTTP_202_ACCEPTED)
def upload_file(file: UploadFile, background: BackgroundTasks, session: SessionDep):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(400, "upload a .kml file or a .zip containing a Shapefile")

    # Only the suffix of the user's filename touches the disk; the name itself is just stored.
    fd, tmp = tempfile.mkstemp(suffix=suffix)
    size = 0
    with os.fdopen(fd, "wb") as out:
        while chunk := file.file.read(1024 * 1024):
            size += len(chunk)
            if size > MAX_UPLOAD_BYTES:
                out.close()
                os.unlink(tmp)
                raise HTTPException(413, "file is larger than 50 MB")
            out.write(chunk)

    record = UploadedFile(filename=file.filename)
    session.add(record)
    session.commit()
    # ponytail: in-process task; a server restart mid-processing leaves the file PROCESSING.
    # Move to a job queue (e.g. Celery, RQ) if uploads get big or the API scales out.
    background.add_task(process_file, record.id, Path(tmp))
    return record


@router.get("/{file_id}/", response_model=FileOut)
def get_file(file_id: uuid.UUID, session: SessionDep):
    return _get_file(session, file_id)


@router.get("/{file_id}/measurements/", response_model=MeasurementPage)
def get_measurements(
    file_id: uuid.UUID,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    file = _get_completed_file(session, file_id)
    total = session.scalar(select(func.count()).where(Feature.file_id == file_id))
    rows = session.scalars(
        select(Feature)
        .where(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
        .limit(limit)
        .offset(offset)
    )
    return MeasurementPage(
        file_id=file_id,
        source_crs=file.crs,
        total=total,
        limit=limit,
        offset=offset,
        items=[MeasurementOut.model_validate(f) for f in rows],
    )


@router.get("/{file_id}/features/")
def get_features(file_id: uuid.UUID, session: SessionDep) -> dict:
    """All features as a GeoJSON FeatureCollection in EPSG:4326, for drawing on a map."""
    _get_completed_file(session, file_id)
    # ponytail: unpaginated; fine for survey-sized files, add bbox filtering for very large ones.
    rows = session.execute(
        select(Feature, func.ST_AsGeoJSON(Feature.geometry))
        .where(Feature.file_id == file_id)
        .order_by(Feature.feature_index)
    )
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": f.feature_index,
                "geometry": json.loads(geojson) if geojson else None,
                "properties": {
                    **f.properties,
                    "area_m2": f.area_m2,
                    "length_m": f.length_m,
                    "reason": f.reason,
                },
            }
            for f, geojson in rows
        ],
    }


def _get_file(session: Session, file_id: uuid.UUID) -> UploadedFile:
    file = session.get(UploadedFile, file_id)
    if file is None:
        raise HTTPException(404, "file not found")
    return file


def _get_completed_file(session: Session, file_id: uuid.UUID) -> UploadedFile:
    file = _get_file(session, file_id)
    if file.status != FileStatus.COMPLETED:
        raise HTTPException(409, f"file is {file.status}, measurements are not available")
    return file
