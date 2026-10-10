import { Fragment, useEffect, useState } from 'react'
import type { FeatureCollection } from 'geojson'
import { GeoJSON, MapContainer, TileLayer, useMap } from 'react-leaflet'
import { circleMarker, geoJSON, type PathOptions } from 'leaflet'
import {
  type Measurement,
  getFeatures,
  getFile,
  getMeasurements,
  uploadFile,
  type FileInfo,
  type MeasurementPage,
} from './api'

const REPO_URL = 'https://github.com/Prathu3110/Geospacial_measurement_api'

const SAMPLES = [
  { file: 'bengaluru-site.kml', title: 'Bengaluru site', detail: 'KML with a polygon, a line and a point' },
  { file: 'bellary-pits-utm43n.zip', title: 'Bellary pits', detail: 'Shapefile already projected to UTM 43N' },
]

// The OSM basemap is light in both themes, so the highlight is one fixed colour that stands out
// against its greens, blues and beiges.
const HIGHLIGHT: PathOptions = { color: '#c2410c', weight: 3, fillColor: '#c2410c', fillOpacity: 0.35 }

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))
const fmt = (value: number | null, digits: number) =>
  value === null ? '-' : value.toLocaleString(undefined, { maximumFractionDigits: digits })

const props = (m: Measurement) =>
  Object.entries(m.properties)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(', ')

function downloadCsv(filename: string, items: Measurement[]) {
  const columns = [
    'feature_index',
    'geometry_type',
    'measurement_crs',
    'area_m2',
    'area_ha',
    'length_m',
    'length_km',
    'reason',
  ] as const
  // Quote every cell so commas and quotes inside values survive.
  const cell = (value: unknown) => `"${String(value ?? '').replace(/"/g, '""')}"`
  const rows = items.map((m) =>
    [...columns.map((c) => cell(m[c])), cell(JSON.stringify(m.properties))].join(','),
  )
  const csv = [[...columns, 'properties'].join(','), ...rows].join('\n')
  const link = document.createElement('a')
  link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
  link.download = `${filename.replace(/\.[^.]+$/, '')}-measurements.csv`
  link.click()
  URL.revokeObjectURL(link.href)
}

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
  const [selected, setSelected] = useState<number | null>(null)

  async function process(chosen: File) {
    setBusy(true)
    setError(null)
    setFile(null)
    setPage(null)
    setFeatures(null)
    setSelected(null)
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

  const current = page?.items.find((m) => m.feature_index === selected)

  return (
    <>
      <nav className="topbar">
        <span className="brand">Geomeasure</span>
        <span className="links">
          <a href="/docs">API docs</a>
          <a href={REPO_URL}>GitHub</a>
        </span>
      </nav>

      <main>
        <header>
          <h1>Measure every feature in a geospatial file.</h1>
          <p className="lede">
            Upload a KML or zipped Shapefile. Each polygon and line is measured in metres, in its
            own UTM zone.
          </p>
        </header>

        <div className="upload">
          <section
            className={`drop ${dragging ? 'dragging' : ''}`}
            onDragOver={(event) => {
              event.preventDefault()
              setDragging(true)
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            <p className="drop-title">Drop a .kml or .zip file here</p>
            <p className="hint">Shapefiles must be zipped with their .shx, .dbf and .prj. Up to 50 MB.</p>
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
          </section>

          <aside className="samples">
            <h2>No file at hand?</h2>
            {SAMPLES.map((s) => (
              <button
                key={s.file}
                className="sample"
                disabled={busy}
                onClick={() => trySample(s.file)}
              >
                <strong>{s.title}</strong>
                <span>{s.detail}</span>
              </button>
            ))}
          </aside>
        </div>

        {error && (
          <p className="alert" role="alert">
            {error}
          </p>
        )}

        {file && (
          <section className="file" aria-live="polite">
            <div className="file-head">
              <div>
                <span className="filename">{file.filename}</span>
                <span className={`pill ${file.status.toLowerCase()}`}>{file.status}</span>
              </div>
              {page && (
                <button className="button" onClick={() => downloadCsv(file.filename, page.items)}>
                  Download CSV
                </button>
              )}
            </div>
            {file.error && <p className="alert">{file.error}</p>}
            {busy && !page && (
              <div className="skeleton" aria-hidden="true">
                <div className="bar" />
                <div className="block" />
              </div>
            )}
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
                  <dd>
                    {fmt(totalArea, 2)} ha
                    <span className="sub">{fmt(totalArea / 100, 4)} km²</span>
                  </dd>
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
          <div className="explore">
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
                // Clicking a shape shows its details and jumps to its row in the table.
                onEachFeature={(feature, layer) => {
                  layer.on('click', () => setSelected(Number(feature.id)))
                  layer.bindTooltip(`Feature ${feature.id}`, { sticky: true })
                }}
              />
              <FitBounds data={features} />
            </MapContainer>

            <aside className="detail">
              {current ? (
                <>
                  <h2>Feature {current.feature_index}</h2>
                  <dl>
                    <dt>Type</dt>
                    <dd>{current.geometry_type}</dd>
                    <dt>Measured in</dt>
                    <dd>{current.measurement_crs ?? '-'}</dd>
                    {current.area_m2 !== null && (
                      <>
                        <dt>Area</dt>
                        <dd>
                          {fmt(current.area_m2, 1)} m²
                          <span className="sub">{fmt(current.area_ha, 4)} ha</span>
                        </dd>
                      </>
                    )}
                    {current.length_m !== null && (
                      <>
                        <dt>Length</dt>
                        <dd>
                          {fmt(current.length_m, 1)} m
                          <span className="sub">{fmt(current.length_km, 3)} km</span>
                        </dd>
                      </>
                    )}
                    {current.reason && (
                      <>
                        <dt>Note</dt>
                        <dd>{current.reason}</dd>
                      </>
                    )}
                    {Object.entries(current.properties).map(([key, value]) => (
                      <Fragment key={key}>
                        <dt>{key}</dt>
                        <dd>{String(value)}</dd>
                      </Fragment>
                    ))}
                  </dl>
                </>
              ) : (
                <p className="hint">Click a shape on the map to see its measurements here.</p>
              )}
            </aside>
          </div>
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
                  <tr
                    key={m.feature_index}
                    className={m.feature_index === selected ? 'selected' : undefined}
                    onClick={() => setSelected(m.feature_index)}
                  >
                    <td>{m.feature_index}</td>
                    <td>{m.geometry_type}</td>
                    <td>{m.measurement_crs ?? '-'}</td>
                    <td className="num">{fmt(m.area_m2, 1)}</td>
                    <td className="num">{fmt(m.area_ha, 4)}</td>
                    <td className="num">{fmt(m.length_m, 1)}</td>
                    <td className="num">{fmt(m.length_km, 3)}</td>
                    <td className="muted" title={m.reason ?? undefined}>
                      {m.reason}
                    </td>
                    <td className="props" title={props(m)}>
                      {props(m)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </>
  )
}
