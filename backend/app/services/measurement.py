from dataclasses import dataclass

import geopandas as gpd
import pandas as pd
from shapely.validation import explain_validity

AREA_TYPES = {"Polygon", "MultiPolygon"}
LENGTH_TYPES = {"LineString", "MultiLineString", "LinearRing"}


@dataclass
class Measurement:
    measurement_crs: str | None = None
    area_m2: float | None = None
    length_m: float | None = None
    reason: str | None = None


def utm_epsg(lon: float, lat: float) -> int:
    # ponytail: ignores the Norway/Svalbard zone exceptions; irrelevant outside 56-84°N, 0-42°E.
    zone = min(int((lon + 180) // 6) + 1, 60)
    return (32600 if lat >= 0 else 32700) + zone


def measure_features(gdf: gpd.GeoDataFrame) -> list[Measurement]:
    """Measure each feature in the UTM zone of its own centre. Expects a 0..n-1 index."""
    results = [Measurement() for _ in range(len(gdf))]

    measurable = []
    for i, geom in enumerate(gdf.geometry):
        if geom is None or geom.is_empty:
            results[i].reason = "empty geometry"
        elif geom.geom_type not in AREA_TYPES | LENGTH_TYPES:
            results[i].reason = f"no measurement for {geom.geom_type}"
        elif not geom.is_valid:
            # Shapely returns a number for a self-intersecting polygon, but it's wrong.
            results[i].reason = f"invalid geometry: {explain_validity(geom)}"
        else:
            measurable.append(i)
    if not measurable:
        return results

    source = gdf.geometry.iloc[measurable]
    # Bounding-box centre picks the zone; precise enough for this and avoids centroid-on-degrees.
    # ponytail: a feature crossing the antimeridian gets a centre near 0° longitude.
    bounds = source.to_crs(4326).bounds
    lons = (bounds.minx + bounds.maxx) / 2
    lats = (bounds.miny + bounds.maxy) / 2
    zones = pd.Series(
        [utm_epsg(lon, lat) for lon, lat in zip(lons, lats, strict=True)], index=source.index
    )

    for epsg, index in zones.groupby(zones).groups.items():
        # Project straight from the source CRS, not via 4326, to avoid a second transformation.
        for i, geom in source.loc[index].to_crs(epsg).items():
            m = results[i]
            m.measurement_crs = f"EPSG:{epsg}"
            if geom.geom_type in AREA_TYPES:
                m.area_m2 = geom.area
            else:
                m.length_m = geom.length
    return results
