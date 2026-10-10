import { useEffect, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import { circleMarker, geoJSON, type PathOptions } from 'leaflet'
import {
  getFeatures,
  getFile,
  getMeasurements,
  uploadFile,
  type FileInfo,
  type MeasurementPage,
} from './api'

const SAMPLES = [
  { file: 'bengaluru-site.kml', label: 'KML: polygon, line, point' },
  { file: 'bellary-pits-utm43n.zip', label: 'Shapefile in UTM 43N' },
]

// The OSM basemap is light in both themes, so the highlight is one fixed colour that stands out
// against its greens, blues and beiges.
const HIGHLIGHT: PathOptions = { color: '#d9480f', weight: 3, fillColor: '#d9480f', fillOpacity: 0.35 }

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const fmt = (value: number | null, digits: number) =>
  value === null ? '-' : value.toLocaleString(undefined, { maximumFractionDigits: digits })

function FitBounds({ data }: { data: FeatureCollection }) {
  const map = useMap()
  useEffect(() => {
    const bounds = geoJSON(data).getBounds()
    if (bounds.isValid()) map.fitBounds(bounds, { padding: [24, 24] })
  }, [map, data])
  return null
}

export default function App() {
  const [file, setFile] = useState<FileInfo | null>(null)
  const [page, setPage] = useState<MeasurementPage | null>(null)
  const [features, setFeatures] = useState<FeatureCollection | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [dragging, setDragging] = useState(false)

  async function process(chosen: File) {
    setBusy(true)
    setError(null)
    setFile(null)
    setPage(null)
    setFeatures(null)
    try {
      let info = await uploadFile(chosen)
      setFile(info)
      while (info.status === 'PENDING' || info.status === 'PROCESSING') {
        await sleep(500)
        info = await getFile(info.id)
        setFile(info)
      }
      if (info.status === 'COMPLETED') {
        const [measurements, collection] = await Promise.all([
          getMeasurements(info.id),
          getFeatures(info.id),
        ])
        setPage(measurements)
        setFeatures(collection)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  async function trySample(name: string) {
    const blob = await (await fetch(`/samples/${name}`)).blob()
    process(new File([blob], name))
  }

  function onDrop(event: React.DragEvent) {
    event.preventDefault()
    setDragging(false)
    const dropped = event.dataTransfer.files[0]
    if (dropped && !busy) process(dropped)
  }

  const totalArea = page?.items.reduce((sum, m) => sum + (m.area_ha ?? 0), 0) ?? 0
  const totalLength = page?.items.reduce((sum, m) => sum + (m.length_km ?? 0), 0) ?? 0

  return (
    <main>
      <header>
        <h1>Geospatial File Measurement</h1>
        <p className="lede">
          Upload a KML file or a zipped Shapefile. Each polygon's area and each line's length is
          measured in the UTM zone where it lies.
        </p>
      </header>

      <section
        className={`drop ${dragging ? 'dragging' : ''}`}
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
      >
        <label className="button primary">
          {busy ? 'Processing…' : 'Choose file'}
          <input
            type="file"
            accept=".kml,.zip"
            disabled={busy}
            onChange={(event) => {
              const chosen = event.target.files?.[0]
              if (chosen) process(chosen)
              event.target.value = ''
            }}
          />
        </label>
        <p className="hint">or drop a .kml or .zip file here, up to 50 MB</p>
        <div className="samples">
          <span className="hint">Try a sample:</span>
          {SAMPLES.map((s) => (
            <button
              key={s.file}
              className="button"
              disabled={busy}
              onClick={() => trySample(s.file)}
            >
              {s.label}
            </button>
          ))}
        </div>
      </section>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {file && (
        <section className="file" aria-live="polite">
          <div>
            <span className="filename">{file.filename}</span>
            <span className={`pill ${file.status.toLowerCase()}`}>{file.status}</span>
          </div>
          {file.error && <p className="alert">{file.error}</p>}
          {page && (
            <dl className="stats">
              <div>
                <dt>Features</dt>
                <dd>{file.feature_count}</dd>
              </div>
              <div>
                <dt>Source CRS</dt>
                <dd>{file.crs}</dd>
              </div>
              <div>
                <dt>Total area</dt>
                <dd>{fmt(totalArea, 2)} ha</dd>
              </div>
              <div>
                <dt>Total length</dt>
                <dd>{fmt(totalLength, 3)} km</dd>
              </div>
            </dl>
          )}
        </section>
      )}

      {features && (
        <MapContainer className="map" center={[0, 0]} zoom={2}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <GeoJSON
            data={features}
            style={HIGHLIGHT}
            // Circles instead of Leaflet's default pin images, which Vite builds don't bundle.
            pointToLayer={(_, latlng) => circleMarker(latlng, { ...HIGHLIGHT, radius: 7 })}
          />
          <FitBounds data={features} />
        </MapContainer>
      )}

      {page && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Type</th>
                <th>Measured in</th>
                <th className="num">Area (m²)</th>
                <th className="num">Area (ha)</th>
                <th className="num">Length (m)</th>
                <th className="num">Length (km)</th>
                <th>Note</th>
                <th>Properties</th>
              </tr>
            </thead>
            <tbody>
              {page.items.map((m) => (
                <tr key={m.feature_index}>
                  <td>{m.feature_index}</td>
                  <td>{m.geometry_type}</td>
                  <td>{m.measurement_crs ?? '-'}</td>
                  <td className="num">{fmt(m.area_m2, 1)}</td>
                  <td className="num">{fmt(m.area_ha, 4)}</td>
                  <td className="num">{fmt(m.length_m, 1)}</td>
                  <td className="num">{fmt(m.length_km, 3)}</td>
                  <td className="muted">{m.reason}</td>
                  <td>
                    <code>{JSON.stringify(m.properties)}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <footer>
        API docs at <a href="/docs">/docs</a>
      </footer>
    </main>
  )
}
