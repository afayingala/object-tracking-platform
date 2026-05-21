import { useState } from 'react'

function TargetIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="2"/>
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>
    </svg>
  )
}

function CheckCircleIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
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

function AlertIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
    </svg>
  )
}

const SLIDERS = [
  {
    field: 'confidence',
    label: 'Detection Confidence',
    desc: 'Minimum confidence score for a detection to be accepted. Higher = fewer but more certain detections.',
    min: 0.1, max: 0.95, step: 0.05,
    Icon: TargetIcon,
    fmt: v => v.toFixed(2),
    minLabel: '0.10', maxLabel: '0.95',
  },
  {
    field: 'max_age',
    label: 'Max Track Age',
    desc: 'Frames to keep a track alive without a detection before terminating it. Raise this for objects that disappear behind occlusions (e.g. 90–300 for sports).',
    min: 1, max: 300, step: 1,
    Icon: ClockIcon,
    fmt: v => `${v}f`,
    minLabel: '1f', maxLabel: '300f',
  },
  {
    field: 'min_hits',
    label: 'Min Confirmation Hits',
    desc: 'Consecutive detections required before a new track is confirmed and displayed.',
    min: 1, max: 10, step: 1,
    Icon: CheckCircleIcon,
    fmt: v => String(v),
    minLabel: '1', maxLabel: '10',
  },
]

export default function ConfigPanel({ filename, config, setConfig, onProcess, onBack }) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  async function handleStart() {
    setError('')
    setLoading(true)
    try { await onProcess() }
    catch (e) { setError(e.message || 'Failed to start processing.') }
    finally { setLoading(false) }
  }

  return (
    <div className="glass panel">
      <h2 className="panel-title">Tune the <span className="grad-text">tracker</span></h2>
      <p className="panel-sub mono" style={{ fontSize: '0.78rem' }}>{filename}</p>

      <div className="config-cards">
        {SLIDERS.map(({ field, label, desc, min, max, step, Icon, fmt, minLabel, maxLabel }) => (
          <div key={field} className="config-card">
            <div className="config-card-header">
              <div className="config-icon-tile"><Icon /></div>
              <div className="config-card-label">
                <div className="config-card-title">{label}</div>
                <div className="config-card-desc">{desc}</div>
              </div>
              <div className="config-card-value">{fmt(config[field])}</div>
            </div>
            <input
              type="range"
              className="config-slider"
              min={min} max={max} step={step}
              value={config[field]}
              onChange={(e) => setConfig({ ...config, [field]: parseFloat(e.target.value) })}
            />
            <div className="config-minmax">
              <span>{minLabel}</span>
              <span>{maxLabel}</span>
            </div>
          </div>
        ))}
      </div>

      {error && (
        <div className="error-pill">
          <AlertIcon />{error}
        </div>
      )}

      <div className="btn-row">
        <button className="btn btn-ghost" onClick={onBack}><ArrowLeftIcon />Back</button>
        <button className="btn btn-primary" onClick={handleStart} disabled={loading}>
          <PlayIcon />{loading ? 'Starting…' : 'Start processing'}
        </button>
      </div>
    </div>
  )
}
