import { useState, useRef, useEffect, useCallback } from 'react'

const ZONE_COLOURS = ['#22c55e', '#f97316', '#a855f7', '#ec4899']
const TARGET_COLOURS = ['#ffc800', '#0090ff']
const MAX_ZONES = 4

function MapPinIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>
    </svg>
  )
}

function ArrowLeftIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="19" y1="12" x2="5" y2="12"/><polyline points="12 19 5 12 12 5"/>
    </svg>
  )
}

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3"/>
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4h6v2"/>
    </svg>
  )
}

function getSVGCoords(e, svgEl) {
  const pt = svgEl.createSVGPoint()
  pt.x = e.clientX
  pt.y = e.clientY
  return pt.matrixTransform(svgEl.getScreenCTM().inverse())
}

export default function ZoneAnalysis({ jobId, videoId, api, onBack }) {
  const [frameData,  setFrameData]  = useState(null)
  const [loadingFrame, setLoadingFrame] = useState(true)
  const [zones,      setZones]      = useState([])
  const [drawing,    setDrawing]    = useState(null)   // {x1,y1,x2,y2} in progress
  const [result,     setResult]     = useState(null)
  const [running,    setRunning]    = useState(false)
  const [imgLoaded,  setImgLoaded]  = useState(false)
  const svgRef = useRef()

  useEffect(() => {
    fetch(`${api}/api/preview/${videoId}`)
      .then(r => r.json())
      .then(d => { setFrameData(d); setLoadingFrame(false) })
      .catch(() => setLoadingFrame(false))
  }, [videoId, api])

  const onMouseDown = useCallback((e) => {
    if (zones.length >= MAX_ZONES) return
    if (!svgRef.current) return
    e.preventDefault()
    const { x, y } = getSVGCoords(e, svgRef.current)
    setDrawing({ x1: x, y1: y, x2: x, y2: y })
  }, [zones.length])

  const onMouseMove = useCallback((e) => {
    if (!drawing || !svgRef.current) return
    const { x, y } = getSVGCoords(e, svgRef.current)
    setDrawing(d => ({ ...d, x2: x, y2: y }))
  }, [drawing])

  const onMouseUp = useCallback((e) => {
    if (!drawing || !svgRef.current) return
    const { x, y } = getSVGCoords(e, svgRef.current)
    const x1 = Math.min(drawing.x1, x), x2 = Math.max(drawing.x1, x)
    const y1 = Math.min(drawing.y1, y), y2 = Math.max(drawing.y1, y)
    if (x2 - x1 > 10 && y2 - y1 > 10) {
      const idx = zones.length
      setZones(zs => [...zs, { id: Date.now(), name: `Zone ${String.fromCharCode(65 + idx)}`, x1, y1, x2, y2 }])
    }
    setDrawing(null)
  }, [drawing, zones.length])

  function removeZone(id) {
    setZones(zs => {
      const filtered = zs.filter(z => z.id !== id)
      return filtered.map((z, i) => ({ ...z, name: `Zone ${String.fromCharCode(65 + i)}` }))
    })
    setResult(null)
  }

  async function runAnalysis() {
    if (!zones.length) return
    setRunning(true)
    setResult(null)
    try {
      const res = await fetch(`${api}/api/zone-analysis/${jobId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zones: zones.map(z => ({ name: z.name, x1: z.x1, y1: z.y1, x2: z.x2, y2: z.y2 })) }),
      })
      const data = await res.json()
      setResult(data)
    } catch {
      // silently fail — user can retry
    }
    setRunning(false)
  }

  if (loadingFrame) return null

  const { frame, width, height } = frameData || {}

  return (
    <div className="glass panel zone-analysis-panel">
      <div className="zone-analysis-header">
        <div className="zone-analysis-title-row">
          <div className="stat-icon-wrap" style={{ color: '#22c55e' }}><MapPinIcon /></div>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-primary)' }}>Zone Dwell <span className="grad-text">Analysis</span></div>
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 2 }}>
              Draw zones on the frame to measure how long each target spends inside them
            </div>
          </div>
          <button className="btn btn-ghost" onClick={onBack} style={{ flexShrink: 0 }}>
            <ArrowLeftIcon />Back to results
          </button>
        </div>
      </div>

      {frame && (
        <div className="zone-frame-wrap">
          <img
            src={`data:image/jpeg;base64,${frame}`}
            alt="Frame for zone drawing"
            className="zone-frame-img"
            onLoad={() => setImgLoaded(true)}
          />

          {imgLoaded && (
            <svg
              ref={svgRef}
              viewBox={`0 0 ${width} ${height}`}
              preserveAspectRatio="none"
              className="zone-frame-svg"
              style={{ cursor: zones.length >= MAX_ZONES ? 'not-allowed' : 'crosshair' }}
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={() => setDrawing(null)}
            >
              {zones.map((z, i) => {
                const colour = ZONE_COLOURS[i % ZONE_COLOURS.length]
                return (
                  <g key={z.id}>
                    <rect
                      x={z.x1} y={z.y1}
                      width={z.x2 - z.x1} height={z.y2 - z.y1}
                      fill={`${colour}22`}
                      stroke={colour}
                      strokeWidth={3}
                      strokeDasharray="8 4"
                    />
                    <rect x={z.x1} y={z.y1 - 26} width={90} height={24} fill={colour} rx={4} />
                    <text
                      x={z.x1 + 8} y={z.y1 - 9}
                      fill="#000" fontSize={14} fontFamily="JetBrains Mono, monospace" fontWeight="700"
                      style={{ pointerEvents: 'none', userSelect: 'none' }}
                    >
                      {z.name}
                    </text>
                  </g>
                )
              })}

              {drawing && (() => {
                const rx = Math.min(drawing.x1, drawing.x2)
                const ry = Math.min(drawing.y1, drawing.y2)
                const rw = Math.abs(drawing.x2 - drawing.x1)
                const rh = Math.abs(drawing.y2 - drawing.y1)
                const colour = ZONE_COLOURS[zones.length % ZONE_COLOURS.length]
                return (
                  <rect
                    x={rx} y={ry} width={rw} height={rh}
                    fill={`${colour}18`}
                    stroke={colour}
                    strokeWidth={2}
                    strokeDasharray="6 3"
                    style={{ pointerEvents: 'none' }}
                  />
                )
              })()}
            </svg>
          )}
        </div>
      )}

      <div className="zone-controls">
        <div className="zone-chips">
          {zones.length === 0 && (
            <span style={{ fontSize: '0.8rem', color: 'var(--text-faint)' }}>
              Click and drag on the frame above to draw a zone
            </span>
          )}
          {zones.map((z, i) => (
            <div key={z.id} className="zone-chip" style={{ borderColor: ZONE_COLOURS[i], background: `${ZONE_COLOURS[i]}18` }}>
              <span className="zone-chip-dot" style={{ background: ZONE_COLOURS[i] }} />
              <span>{z.name}</span>
              <button className="zone-chip-remove" onClick={() => removeZone(z.id)}>
                <TrashIcon />
              </button>
            </div>
          ))}
        </div>

        <button
          className="btn btn-primary"
          disabled={zones.length === 0 || running}
          onClick={runAnalysis}
          style={{ minWidth: 160 }}
        >
          <PlayIcon />
          {running ? 'Analysing…' : 'Run Analysis'}
        </button>
      </div>

      {result && (
        <div className="zone-results">
          <div className="zone-results-title">Results</div>
          {result.targets.map((target, ti) => (
            <div key={target.target_id} className="zone-target-block">
              <div className="zone-target-label">
                <span className="zone-target-dot" style={{ background: TARGET_COLOURS[ti % 2] }} />
                Target {target.target_id} — <span className="mono">{target.class_name}</span>
              </div>
              <div className="zone-result-table-wrap">
                <table className="zone-result-table">
                  <thead>
                    <tr>
                      <th>Zone</th>
                      <th>Dwell time</th>
                      <th>Visits</th>
                      <th>Frames</th>
                    </tr>
                  </thead>
                  <tbody>
                    {target.zones.map((z, zi) => (
                      <tr key={z.zone_name}>
                        <td>
                          <span className="zone-chip-dot" style={{ background: ZONE_COLOURS[zi], display: 'inline-block', marginRight: 6 }} />
                          {z.zone_name}
                        </td>
                        <td className="zone-dwell">{z.dwell_seconds > 0 ? `${z.dwell_seconds}s` : '—'}</td>
                        <td>{z.visit_count > 0 ? z.visit_count : '—'}</td>
                        <td className="mono" style={{ color: 'var(--text-faint)', fontSize: '0.78rem' }}>{z.frames_in_zone}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
