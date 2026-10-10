import json
import logging
import uuid
from pathlib import Path

import shapely
from geoalchemy2.shape import from_shape
from pyproj import CRS

from app.db import SessionLocal
from app.models import Feature, FileStatus, UploadedFile
from app.services.measurement import measure_features
from app.services.readers import InvalidUpload, read_features

log = logging.getLogger(__name__)

# Values LIBKML fills in for placemarks that don't set them; they say nothing about the feature.
KML_DEFAULTS = {"extrude": 0, "tessellate": -1, "visibility": -1}


def process_file(file_id: uuid.UUID, path: Path) -> None:
    """Read, measure and store every feature. Runs after the upload response is sent."""
    with SessionLocal() as session:
        file = session.get(UploadedFile, file_id)
        file.status = FileStatus.PROCESSING
        session.commit()

        try:
            gdf = read_features(path)
            measurements = measure_features(gdf)
            properties = _properties(gdf, kml=path.suffix.lower() == ".kml")
            wgs84 = gdf.geometry.to_crs(4326)

            for i, (geom, m) in enumerate(zip(wgs84, measurements, strict=True)):
                # Z is dropped: measurements are 2D and the column is 2D.
                shape = shapely.force_2d(geom) if geom is not None and not geom.is_empty else None
                session.add(
                    Feature(
                        file_id=file_id,
                        feature_index=i,
                        geometry_type=geom.geom_type if geom is not None else None,
                        geometry=from_shape(shape, srid=4326) if shape is not None else None,
                        properties=properties[i],
                        measurement_crs=m.measurement_crs,
                        area_m2=m.area_m2,
                        length_m=m.length_m,
                        reason=m.reason,
                    )
                )
            file.crs = _crs_label(gdf.crs)
            file.feature_count = len(gdf)
            file.status = FileStatus.COMPLETED
        except InvalidUpload as exc:
            session.rollback()
            file.status, file.error = FileStatus.FAILED, str(exc)
        except Exception:
            log.exception("processing failed for file %s", file_id)
            session.rollback()
            file.status, file.error = FileStatus.FAILED, "internal error while processing file"
        finally:
            path.unlink(missing_ok=True)
        session.commit()


def _crs_label(crs: CRS) -> str:
    epsg = crs.to_epsg()
    return f"EPSG:{epsg}" if epsg else crs.name


def _properties(gdf, kml: bool) -> list[dict]:
    # pandas' JSON encoder turns NaN/NaT/numpy types into JSON-safe values in one step.
    table = gdf.drop(columns=gdf.geometry.name)
    rows = json.loads(table.to_json(orient="records", date_format="iso"))
    # LIBKML adds many always-empty columns (drawOrder, icon, ...); drop nulls to keep it readable.
    defaults = KML_DEFAULTS if kml else {}
    return [
        {k: v for k, v in row.items() if v is not None and defaults.get(k, object()) != v}
        for row in rows
    ]
