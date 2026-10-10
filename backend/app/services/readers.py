import zipfile
from pathlib import Path

import geopandas as gpd
import pandas as pd
import pyogrio
from pyogrio.errors import DataLayerError, DataSourceError

# Guards against zip bombs: a small upload that inflates to gigabytes.
MAX_UNZIPPED_BYTES = 500 * 1024 * 1024


class InvalidUpload(ValueError):
    """The file can't be read as KML or a zipped Shapefile. The message is safe to show users."""


def read_features(path: Path) -> gpd.GeoDataFrame:
    suffix = path.suffix.lower()
    if suffix == ".kml":
        gdf = _read_kml(path)
    elif suffix == ".zip":
        gdf = _read_shapefile_zip(path)
    else:
        raise InvalidUpload("expected a .kml file or a .zip containing a Shapefile")

    if gdf.crs is None:
        raise InvalidUpload("file has no coordinate reference system")
    return gdf.reset_index(drop=True)


def _read_kml(path: Path) -> gpd.GeoDataFrame:
    # Each KML <Folder> becomes its own layer; reading only the first would silently drop features.
    try:
        layers = pyogrio.list_layers(path)[:, 0]
        frames = [gpd.read_file(path, layer=name).assign(layer=name) for name in layers]
    except (DataSourceError, DataLayerError) as exc:
        raise InvalidUpload("could not parse KML") from exc
    if not frames:
        raise InvalidUpload("KML contains no layers")
    return pd.concat(frames, ignore_index=True)


def _read_shapefile_zip(path: Path) -> gpd.GeoDataFrame:
    try:
        with zipfile.ZipFile(path) as zf:
            # macOS Finder adds __MACOSX/ resource-fork copies, including a fake ._name.shp.
            infos = [i for i in zf.infolist() if not i.is_dir() and "__MACOSX" not in i.filename]
    except zipfile.BadZipFile as exc:
        raise InvalidUpload("file is not a valid zip archive") from exc

    if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
        raise InvalidUpload("zip contents are too large")

    names = {i.filename.lower(): i.filename for i in infos}
    shps = [name for lower, name in names.items() if lower.endswith(".shp")]
    if len(shps) != 1:
        raise InvalidUpload(f"zip must contain exactly one .shp file, found {len(shps)}")

    stem = shps[0][:-4].lower()
    # Without .prj we can't know if coordinates are degrees, metres or feet, so refuse to guess.
    missing = [ext for ext in (".shx", ".dbf", ".prj") if stem + ext not in names]
    if missing:
        raise InvalidUpload(f"Shapefile is missing required parts: {', '.join(missing)}")

    # GDAL reads straight from the archive, so nothing is extracted to disk (no zip-slip risk).
    try:
        return gpd.read_file(f"/vsizip/{path.resolve()}/{shps[0]}")
    except (DataSourceError, DataLayerError) as exc:
        raise InvalidUpload("could not parse Shapefile") from exc
