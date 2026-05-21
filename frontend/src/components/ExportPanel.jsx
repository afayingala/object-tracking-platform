export default function ExportPanel({ jobId, api, onReset }) {
  function download(type) {
    const url = type === 'video'
      ? `${api}/api/download/video/${jobId}`
      : `${api}/api/download/json/${jobId}`
    const a = document.createElement('a')
    a.href = url
    a.download = type === 'video' ? 'tracked_output.mp4' : 'tracking_data.json'
    a.click()
  }

  return (
    <div className="panel">
      <h2 className="panel-title">Export Results</h2>
      <div className="export-grid">
        <div className="export-card" onClick={() => download('video')}>
          <span className="export-icon">&#127902;</span>
          <div>
            <div className="export-title">Annotated Video</div>
            <div className="export-desc">MP4 with bounding boxes, IDs &amp; trajectories</div>
          </div>
          <button className="btn btn-primary">Download</button>
        </div>
        <div className="export-card" onClick={() => download('json')}>
          <span className="export-icon">&#128196;</span>
          <div>
            <div className="export-title">Tracking Data</div>
            <div className="export-desc">JSON with per-frame coordinates and track history</div>
          </div>
          <button className="btn btn-primary">Download</button>
        </div>
      </div>
      <div className="btn-row" style={{ marginTop: '1.5rem' }}>
        <button className="btn btn-secondary" onClick={onReset}>&#8635; Analyse Another Video</button>
      </div>
    </div>
  )
}
