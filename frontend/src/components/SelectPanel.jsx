import { useState, useEffect, useRef } from 'react'

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

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  )
}

// Amber for T1, blue for T2 — matches the pipeline's TARGET_COLORS
const TARGET_COLOURS = ['#ffc800', '#0090ff']

function key(det) {
  return `${det.x1},${det.y1},${det.x2},${det.y2}`
}

export default function SelectPanel({ videoId, api, onSelect, onBack }) {
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState('')
  const [frameData, setFrameData] = useState(null)   // {frame, width, height, detections}
  const [selected,  setSelected]  = useState([])     // up to 2 detection dicts
  const [imgLoaded, setImgLoaded] = useState(false)
  const imgRef = useRef()

  useEffect(() => {
    fetch(`${api}/api/preview/${videoId}`)
      .then(r => { if (!r.ok) throw new Error('Preview failed.'); return r.json() })
      .then(data => { setFrameData(data); setLoading(false) })
      .catch(e  => { setError(e.message || 'Could not load preview frame.'); setLoading(false) })
  }, [videoId, api])

  function toggleDet(det) {
    const k = key(det)
    const already = selected.findIndex(s => key(s) === k)
    if (already !== -1) {
      setSelected(selected.filter((_, i) => i !== already))
    } else if (selected.length < 2) {
      setSelected([...selected, det])
    }
  }

  function selIdx(det) {
    return selected.findIndex(s => key(s) === key(det))
  }

  const handleContinue = () => onSelect(selected)

  return (
    <div className="glass panel">
      <h2 className="panel-title">Select <span className="grad-text">targets</span></h2>
      <p className="panel-sub">
        Click up to 2 objects to track. Objects must be visible in this frame.
        Selected objects will be tracked through their every appearance, including re-entries.
      </p>

      {loading && (
        <div className="select-loading">
          <svg className="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ width: 24, height: 24 }}>
            <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
          </svg>
          <span>Extracting preview frame…</span>
        </div>
      )}

      {error && (
        <div className="error-pill"><AlertIcon />{error}</div>
      )}

      {frameData && (
        <>
          {/* ── Frame with clickable detection overlays ── */}
          <div className="select-frame-container">
            <img
              ref={imgRef}
              src={`data:image/jpeg;base64,${frameData.frame}`}
              alt="First frame preview"
              className="select-frame-img"
              onLoad={() => setImgLoaded(true)}
            />

            {imgLoaded && (
              <svg
                viewBox={`0 0 ${frameData.width} ${frameData.height}`}
                preserveAspectRatio="none"
                className="select-frame-svg"
              >
                {frameData.detections.map((det, i) => {
                  const si = selIdx(det)
                  const isSel = si !== -1
                  const colour = isSel ? TARGET_COLOURS[si] : 'rgba(255,255,255,0.75)'
                  const fillOp = isSel ? '0.18' : '0.04'
                  const bw     = isSel ? 3 : 1.5

                  return (
                    <g key={i} onClick={() => toggleDet(det)} style={{ cursor: 'pointer' }}>
                      <rect
                        x={det.x1} y={det.y1}
                        width={det.x2 - det.x1} height={det.y2 - det.y1}
                        fill={`${isSel ? (si === 0 ? 'rgba(255,200,0,' : 'rgba(0,144,255,') : 'rgba(255,255,255,'}${fillOp})`}
                        stroke={colour}
                        strokeWidth={bw}
                      />
                      {/* hit-area: slightly larger transparent rect for easier clicking */}
                      <rect
                        x={det.x1 - 6} y={det.y1 - 6}
                        width={det.x2 - det.x1 + 12} height={det.y2 - det.y1 + 12}
                        fill="transparent"
                      />
                      {/* Label chip */}
                      <rect
                        x={det.x1} y={det.y1 - 22}
                        width={Math.max(60, (isSel ? 32 : det.class_name.length * 8 + 10))}
                        height={22}
                        fill={isSel ? colour : 'rgba(0,0,0,0.55)'}
                        rx={4}
                      />
                      <text
                        x={det.x1 + 5} y={det.y1 - 6}
                        fill={isSel && si === 0 ? '#000' : '#fff'}
                        fontSize={13}
                        fontFamily="JetBrains Mono, monospace"
                        fontWeight="600"
                        style={{ pointerEvents: 'none', userSelect: 'none' }}
                      >
                        {isSel ? `T${si + 1}` : det.class_name}
                      </text>
                    </g>
                  )
                })}
              </svg>
            )}
          </div>

          {/* ── Selection status chips ── */}
          <div className="select-status-row">
            {[0, 1].map(i => {
              const t = selected[i]
              return (
                <div
                  key={i}
                  className={`select-slot ${t ? 'filled' : 'empty'}`}
                  style={t ? { borderColor: TARGET_COLOURS[i], background: `${TARGET_COLOURS[i]}18` } : {}}
                >
                  <div className="select-slot-dot" style={{ background: t ? TARGET_COLOURS[i] : undefined }} />
                  <span className="select-slot-label">
                    {t ? `Target ${i + 1} — ${t.class_name}` : `Target ${i + 1} — not selected`}
                  </span>
                  {t && (
                    <button className="select-slot-remove" onClick={() => toggleDet(t)}>✕</button>
                  )}
                </div>
              )
            })}
          </div>

          {frameData.detections.length === 0 && (
            <div className="error-pill" style={{ marginTop: '1rem' }}>
              <AlertIcon />
              No objects detected in the first frame. Try a different video or lower the confidence threshold in the next step.
            </div>
          )}
        </>
      )}

      <div className="btn-row" style={{ marginTop: '1.5rem' }}>
        <button className="btn btn-ghost" onClick={onBack}><ArrowLeftIcon />Back</button>
        <button
          className="btn btn-primary"
          disabled={selected.length === 0}
          onClick={handleContinue}
        >
          <PlayIcon />
          {selected.length === 0
            ? 'Select a target'
            : `Track ${selected.length} target${selected.length > 1 ? 's' : ''}`}
        </button>
      </div>
    </div>
  )
}
