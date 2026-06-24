function CheckIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ width: 16, height: 16 }}>
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}

function LoaderIcon() {
  return (
    <svg className="spin" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ width: 16, height: 16 }}>
      <path d="M21 12a9 9 0 1 1-6.219-8.56"/>
    </svg>
  )
}

function CircleIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ width: 10, height: 10 }}>
      <circle cx="12" cy="12" r="5"/>
    </svg>
  )
}

const STAGES = [
  'Frame extraction',
  'YOLO candidate detection',
  'IoU / appearance matching',
  'Re-identification scan',
  'Generating annotated output',
]

export default function ProcessingPanel({ progress, status, errorMsg }) {
  return (
    <div className="glass panel">
      <h2 className="panel-title">Processing your <span className="grad-text">video</span></h2>
      <p className="panel-sub">
        {status === 'queued' ? 'Job queued, starting soon…'
          : status === 'error' ? 'An error occurred during processing.'
          : 'Running detection and tracking pipeline…'}
      </p>

      <div className="proc-header">
        <span className="proc-label">Overall progress</span>
        <span className="proc-pct">{progress}%</span>
      </div>

      <div className="progress-track">
        <div className="progress-fill" style={{ width: `${progress}%` }} />
      </div>

      <div className="proc-stages">
        {STAGES.map((name, i) => {
          const threshold = (i + 1) * 20
          const done   = progress >= threshold
          const active = !done && progress >= threshold - 20
          const state  = done ? 'done' : active ? 'active' : 'pending'
          return (
            <div key={name} className={`proc-stage ${state}`}>
              <div className={`proc-dot ${state}`}>
                {done   ? <CheckIcon /> :
                 active ? <LoaderIcon /> :
                 <CircleIcon />}
              </div>
              <span className="proc-stage-name">{name}</span>
              <span className={`proc-badge ${state}`}>
                {done ? 'Done' : active ? 'Running' : 'Pending'}
              </span>
            </div>
          )
        })}
      </div>

      {status === 'error' && (
        <div className="error-pill" style={{ marginTop: '1.25rem', borderRadius: 'var(--radius)' }}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" style={{ width: 15, height: 15, flexShrink: 0 }}>
            <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>
            <strong>Processing failed.</strong>
            {errorMsg && <> — <span style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: '0.78rem', wordBreak: 'break-all' }}>{errorMsg}</span></>}
          </span>
        </div>
      )}
    </div>
  )
}
