export default function ResultsDashboard({ summary }) {
  const {
    total_objects, class_counts, total_frames,
    fps, avg_track_duration_frames, processing_time_seconds,
  } = summary

  const cards = [
    { label: 'Total Objects Tracked', value: total_objects, icon: '&#128065;' },
    { label: 'Total Frames', value: total_frames, icon: '&#127916;' },
    { label: 'Video FPS', value: fps, icon: '&#9193;' },
    { label: 'Avg Track Duration', value: `${avg_track_duration_frames} frames`, icon: '&#128336;' },
    { label: 'Processing Time', value: `${processing_time_seconds}s`, icon: '&#9889;' },
  ]

  return (
    <div className="panel">
      <h2 className="panel-title">Tracking Results</h2>

      <div className="stats-grid">
        {cards.map((c) => (
          <div key={c.label} className="stat-card">
            <span className="stat-icon" dangerouslySetInnerHTML={{ __html: c.icon }} />
            <div>
              <div className="stat-value">{c.value}</div>
              <div className="stat-label">{c.label}</div>
            </div>
          </div>
        ))}
      </div>

      {Object.keys(class_counts).length > 0 && (
        <div className="class-breakdown">
          <h3>Objects by Class</h3>
          <div className="class-bars">
            {Object.entries(class_counts)
              .sort((a, b) => b[1] - a[1])
              .map(([cls, count]) => (
                <div key={cls} className="class-row">
                  <span className="class-name">{cls}</span>
                  <div className="class-bar-wrap">
                    <div
                      className="class-bar"
                      style={{ width: `${Math.min(100, (count / total_objects) * 100)}%` }}
                    />
                  </div>
                  <span className="class-count">{count}</span>
                </div>
              ))}
          </div>
        </div>
      )}
    </div>
  )
}
