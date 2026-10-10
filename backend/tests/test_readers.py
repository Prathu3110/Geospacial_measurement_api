import zipfile

import geopandas as gpd
import pytest
from shapely.geometry import box

from app.services.readers import InvalidUpload, read_features

KML = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Folder><name>Pits</name>
  <Placemark><name>Pit A</name>
    <ExtendedData><Data name="owner"><value>Client X</value></Data></ExtendedData>
    <Polygon><outerBoundaryIs><LinearRing><coordinates>
      77.59,12.97 77.60,12.97 77.60,12.98 77.59,12.98 77.59,12.97
    </coordinates></LinearRing></outerBoundaryIs></Polygon>
  </Placemark>
</Folder>
<Folder><name>Roads</name>
  <Placemark><name>Haul road</name>
    <LineString><coordinates>77.58,12.96,900 77.61,12.98,910</coordinates></LineString>
  </Placemark>
  <Placemark><name>Marker</name><Point><coordinates>77.595,12.975</coordinates></Point></Placemark>
</Folder>
</Document></kml>
"""


@pytest.fixture
def shapefile_dir(tmp_path):
    gdf = gpd.GeoDataFrame(
        {"name": ["Pit A"]}, geometry=[box(500_000, 1_434_000, 501_000, 1_435_000)], crs=32643
    )
    out = tmp_path / "shp"
    out.mkdir()
    gdf.to_file(out / "pits.shp")
    return out


def zip_dir(directory, zip_path, skip=()):
    with zipfile.ZipFile(zip_path, "w") as zf:
        for f in directory.iterdir():
            if f.suffix not in skip:
                zf.write(f, f"survey/{f.name}")  # nested folder, as users zip it
    return zip_path


def test_kml_reads_features_from_every_folder(tmp_path):
    path = tmp_path / "survey.kml"
    path.write_text(KML)

    gdf = read_features(path)

    assert gdf.crs.to_epsg() == 4326
    assert list(gdf["Name"]) == ["Pit A", "Haul road", "Marker"]
    assert list(gdf["layer"]) == ["Pits", "Roads", "Roads"]
    assert list(gdf.geom_type) == ["Polygon", "LineString", "Point"]
    assert gdf.loc[0, "owner"] == "Client X"


def test_shapefile_zip_keeps_its_projected_crs(shapefile_dir, tmp_path):
    gdf = read_features(zip_dir(shapefile_dir, tmp_path / "pits.zip"))

    assert gdf.crs.to_epsg() == 32643
    assert list(gdf["name"]) == ["Pit A"]
    assert gdf.geometry.iloc[0].area == pytest.approx(1_000_000)


def test_shapefile_without_prj_is_rejected(shapefile_dir, tmp_path):
    path = zip_dir(shapefile_dir, tmp_path / "pits.zip", skip={".prj"})

    with pytest.raises(InvalidUpload, match=r"missing required parts: \.prj"):
        read_features(path)


def test_zip_with_two_shapefiles_is_rejected(shapefile_dir, tmp_path):
    path = zip_dir(shapefile_dir, tmp_path / "pits.zip")
    with zipfile.ZipFile(path, "a") as zf:
        zf.write(shapefile_dir / "pits.shp", "other.shp")

    with pytest.raises(InvalidUpload, match="exactly one .shp file, found 2"):
        read_features(path)


def test_macos_metadata_in_zip_is_ignored(shapefile_dir, tmp_path):
    path = zip_dir(shapefile_dir, tmp_path / "pits.zip")
    with zipfile.ZipFile(path, "a") as zf:
        # What Finder's "Compress" adds next to the real files.
        zf.writestr("__MACOSX/survey/._pits.shp", b"mac resource fork")

    gdf = read_features(path)

    assert list(gdf["name"]) == ["Pit A"]


@pytest.mark.parametrize(
    ("name", "content", "message"),
    [
        ("survey.zip", b"not a zip", "not a valid zip"),
        ("survey.kml", b"<kml><broken", "could not parse KML"),
        ("survey.geojson", b"{}", "expected a .kml file"),
    ],
)
def test_bad_files_raise_invalid_upload(tmp_path, name, content, message):
    path = tmp_path / name
    path.write_bytes(content)

    with pytest.raises(InvalidUpload, match=message):
        read_features(path)
