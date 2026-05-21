import { useEffect, useRef } from 'react'

function EyeIcon()      { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg> }
function FilmIcon()     { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"/><line x1="7" y1="2" x2="7" y2="22"/><line x1="17" y1="2" x2="17" y2="22"/><line x1="2" y1="12" x2="22" y2="12"/><line x1="2" y1="7" x2="7" y2="7"/><line x1="2" y1="17" x2="7" y2="17"/><line x1="17" y1="7" x2="22" y2="7"/><line x1="17" y1="17" x2="22" y2="17"/></svg> }
function ZapIcon()      { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg> }
function ClockIcon()    { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg> }
function CpuIcon()      { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="4" y="4" width="16" height="16" rx="2" ry="2"/><rect x="9" y="9" width="6" height="6"/><line x1="9" y1="1" x2="9" y2="4"/><line x1="15" y1="1" x2="15" y2="4"/><line x1="9" y1="20" x2="9" y2="23"/><line x1="15" y1="20" x2="15" y2="23"/><line x1="20" y1="9" x2="23" y2="9"/><line x1="20" y1="14" x2="23" y2="14"/><line x1="1" y1="9" x2="4" y2="9"/><line x1="1" y1="14" x2="4" y2="14"/></svg> }
function DownloadIcon() { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg> }
function FileJsonIcon() { return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M10 13a1 1 0 0 0-1 1v1a1 1 0 0 1-1 1"/><path d="M14 13a1 1 0 0 1 1 1v1a1 1 0 0 0 1 1"/></svg> }
function RotateCcwIcon(){ return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 .49-4.95"/></svg> }

const STAT_DEFS = [
  { key: 'total_objects',             unit: 'OBJECTS',  caption: 'Total tracked',    Icon: EyeIcon,   fmt: v => String(v) },
  { key: 'total_frames',              unit: 'FRAMES',   caption: 'Total processed',  Icon: FilmIcon,  fmt: v => String(v) },
  { key: 'fps',                       unit: 'FPS',      caption: 'Video frame rate', Icon: ZapIcon,   fmt: v => String(v) },
  { key: 'avg_track_duration_frames', unit: 'AVG LIFE', caption: 'Track duration',   Icon: ClockIcon, fmt: v => `${v}f`  },
  { key: 'processing_time_seconds',   unit: 'PROC TIME',caption: 'Wall-clock time',  Icon: CpuIcon,   fmt: v => `${v}s`  },
]

function ClassBars({ classCounts, total }) {
  const barRefs = useRef([])
  const entries = Object.entries(classCounts).sort((a, b) => b[1] - a[1])

  useEffect(() => {
    const timer = setTimeout(() => {
      entries.forEach(([, count], i) => {
        if (barRefs.current[i]) {
          barRefs.current[i].style.width = `${Math.min(100, (count / total) * 100)}%`
        }
      })
    }, 120)
    return () => clearTimeout(timer)
  }, [])

  return (
    <div className="glass classes-card" style={{ borderRadius: 'var(--radius-lg)' }}>
      <div className="classes-title">Detected classes</div>
      <div className="class-rows">
        {entries.map(([cls, count], i) => (
          <div key={cls} className="class-row" style={{ animationDelay: `${i * 80}ms` }}>
            <div className="class-row-header">
              <span className="class-name">{cls}</span>
              <span className="class-count">{count}</span>
            </div>
            <div className="class-bar-track">
              <div
                ref={el => barRefs.current[i] = el}
                className="class-bar-fill"
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function ResultsView({ summary, jobId, api, onReset }) {
  const { total_objects, class_counts, total_frames, fps, avg_track_duration_frames, processing_time_seconds } = summary
  const videoSrc = `${api}/api/download/video/${jobId}`

  function download(type) {
    const url = type === 'video' ? `${api}/api/download/video/${jobId}` : `${api}/api/download/json/${jobId}`
    const a = document.createElement('a')
    a.href = url
    a.download = type === 'video' ? 'tracked_output.mp4' : 'tracking_data.json'
    a.click()
  }

  const summaryMap = { total_objects, total_frames, fps, avg_track_duration_frames, processing_time_seconds }

  return (
    <div>
      <div className="results-header">
        <h2 className="results-title">Analysis <span className="grad-text">complete</span></h2>
        <button className="btn btn-ghost" onClick={onReset}>
          <RotateCcwIcon />New video
        </button>
      </div>

      {/* Stats */}
      <div className="stats-grid">
        {STAT_DEFS.map(({ key, unit, caption, Icon, fmt }, i) => (
          <div key={key} className="stat-card glass" style={{ animationDelay: `${i * 60}ms` }}>
            <div className="stat-icon-wrap"><Icon /></div>
            <div className="stat-unit">{unit}</div>
            <div className="stat-value">{fmt(summaryMap[key])}</div>
            <div className="stat-caption">{caption}</div>
          </div>
        ))}
      </div>

      {/* Video + Classes */}
      <div className="results-bottom">
        <div className="video-card">
          <video key={jobId} controls src={videoSrc}>Your browser does not support video.</video>
        </div>

        {Object.keys(class_counts).length > 0 && (
          <ClassBars classCounts={class_counts} total={total_objects} />
        )}
      </div>

      {/* Export */}
      <div className="glass panel" style={{ marginTop: '1rem' }}>
        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', fontFamily: 'JetBrains Mono, monospace', marginBottom: '0.25rem' }}>Export results</div>
        <div className="export-tiles">
          <div className="export-tile gold" onClick={() => download('video')}>
            <div className="export-tile-icon"><DownloadIcon /></div>
            <div className="export-tile-name">Annotated Video</div>
            <div className="export-tile-meta">tracked_output.mp4</div>
          </div>
          <div className="export-tile accent" onClick={() => download('json')}>
            <div className="export-tile-icon"><FileJsonIcon /></div>
            <div className="export-tile-name">Tracking Data</div>
            <div className="export-tile-meta">tracking_data.json</div>
          </div>
        </div>
      </div>
    </div>
  )
}
