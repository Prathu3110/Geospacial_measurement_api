import geopandas as gpd
import pytest
from pyproj import Geod
from shapely.geometry import LineString, MultiPolygon, Point, Polygon, box

from app.services.measurement import measure_features, utm_epsg

GEOD = Geod(ellps="WGS84")


def geodesic_area(geom) -> float:
    # pyproj's ellipsoidal area is the independent reference our UTM numbers must agree with.
    return abs(GEOD.geometry_area_perimeter(geom)[0])


@pytest.mark.parametrize(
    ("lon", "lat", "expected"),
    [
        (77.59, 12.97, 32643),  # Bengaluru
        (75.1, 15.2, 32643),  # Bellary, from Lesson 1
        (-43.2, -22.9, 32723),  # Rio de Janeiro, southern hemisphere
        (-180.0, 0.0, 32601),
        (180.0, 0.0, 32660),  # 180° would compute zone 61
    ],
)
def test_utm_epsg(lon, lat, expected):
    assert utm_epsg(lon, lat) == expected


def test_one_km_square_in_utm_is_one_million_m2():
    square = gpd.GeoSeries([box(500_000, 1_434_000, 501_000, 1_435_000)], crs=32643)
    gdf = gpd.GeoDataFrame(geometry=square.to_crs(4326))

    [m] = measure_features(gdf)

    assert m.measurement_crs == "EPSG:32643"
    assert m.area_m2 == pytest.approx(1_000_000, rel=1e-6)
    assert m.length_m is None


def test_polygon_area_matches_geodesic_area():
    pit = Polygon([(77.59, 12.97), (77.60, 12.97), (77.60, 12.98), (77.59, 12.98)])
    gdf = gpd.GeoDataFrame(geometry=[pit], crs=4326)

    [m] = measure_features(gdf)

    # UTM area error peaks around 0.19% at a zone edge on the equator; here it is 0.12%.
    assert m.area_m2 == pytest.approx(geodesic_area(pit), rel=2e-3)


def test_line_length_matches_geodesic_length():
    road = LineString([(77.58, 12.96, 900), (77.61, 12.98, 910)])
    gdf = gpd.GeoDataFrame(geometry=[road], crs=4326)

    [m] = measure_features(gdf)

    expected = GEOD.line_length([77.58, 77.61], [12.96, 12.98])
    assert m.length_m == pytest.approx(expected, rel=2e-3)
    assert m.area_m2 is None


def test_web_mercator_input_is_reprojected_not_measured_directly():
    near_oslo = box(10.70, 59.90, 10.75, 59.93)
    gdf = gpd.GeoDataFrame(geometry=[near_oslo], crs=4326).to_crs(3857)
    assert gdf.geometry.iloc[0].area > 3.5 * geodesic_area(near_oslo)  # the trap

    [m] = measure_features(gdf)

    assert m.measurement_crs == "EPSG:32632"
    assert m.area_m2 == pytest.approx(geodesic_area(near_oslo), rel=2e-3)


def test_features_in_different_zones_use_their_own_zone():
    gdf = gpd.GeoDataFrame(
        geometry=[box(77.59, 12.97, 77.60, 12.98), box(-43.21, -22.91, -43.20, -22.90)], crs=4326
    )

    zones = [m.measurement_crs for m in measure_features(gdf)]

    assert zones == ["EPSG:32643", "EPSG:32723"]


def test_multipolygon_area_is_sum_of_parts():
    a, b = box(77.59, 12.97, 77.60, 12.98), box(77.61, 12.97, 77.62, 12.98)
    gdf = gpd.GeoDataFrame(geometry=[MultiPolygon([a, b])], crs=4326)

    [m] = measure_features(gdf)

    assert m.area_m2 == pytest.approx(geodesic_area(a) + geodesic_area(b), rel=2e-3)


def test_unmeasurable_geometries_get_a_reason_instead_of_crashing():
    bowtie = Polygon([(0, 0), (1, 1), (1, 0), (0, 1)])
    gdf = gpd.GeoDataFrame(geometry=[Point(77.59, 12.97), bowtie, Polygon(), None], crs=4326)

    results = measure_features(gdf)

    assert [m.reason for m in results] == [
        "no measurement for Point",
        "invalid geometry: Self-intersection[0.5 0.5]",
        "empty geometry",
        "empty geometry",
    ]
    assert all(m.area_m2 is None and m.length_m is None for m in results)
