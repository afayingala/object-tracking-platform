export default function VideoPlayer({ jobId, api }) {
  const src = `${api}/api/download/video/${jobId}`

  return (
    <div className="panel">
      <h2 className="panel-title">Annotated Output Video</h2>
      <p className="panel-sub">Bounding boxes, object IDs, and movement trajectories overlaid.</p>
      <div className="video-wrap">
        <video
          key={jobId}
          controls
          className="output-video"
          src={src}
        >
          Your browser does not support the video element.
        </video>
      </div>
    </div>
  )
}
