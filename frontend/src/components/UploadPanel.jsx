import { useState, useRef } from 'react'

function UploadCloudIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="16 16 12 12 8 16"/><line x1="12" y1="12" x2="12" y2="21"/>
      <path d="M20.39 18.39A5 5 0 0 0 18 9h-1.26A8 8 0 1 0 3 16.3"/>
    </svg>
  )
}

function FileVideoIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
      <polyline points="14 2 14 8 20 8"/>
      <polygon points="10 11 16 14.5 10 18 10 11"/>
    </svg>
  )
}

function XIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
      <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
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

function PlayIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3"/>
    </svg>
  )
}

function fmt(bytes) {
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}

export default function UploadPanel({ onUpload }) {
  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [error, setError] = useState('')
  const [picked, setPicked] = useState(null)
  const inputRef = useRef()

  function pickFile(file) {
    if (!file) return
    const ext = file.name.split('.').pop().toLowerCase()
    if (!['mp4', 'avi', 'mov', 'mkv'].includes(ext)) {
      setError('Unsupported format. Use MP4, AVI, MOV, or MKV.')
      return
    }
    setError('')
    setPicked(file)
  }

  async function handleContinue() {
    if (!picked) return
    setUploading(true)
    try {
      await onUpload(picked)
    } catch (e) {
      setError(e.message || 'Upload failed.')
    } finally {
      setUploading(false)
    }
  }

  return (
    <div className="glass panel">
      <h2 className="upload-heading">
        Upload your <span className="grad-text">footage</span>
      </h2>
      <p className="upload-sub">Drop a video file to begin tracking objects with YOLOv8 + Deep SORT.</p>

      <div
        className={`dropzone ${dragging ? 'drag-over' : ''}`}
        onClick={() => !picked && inputRef.current.click()}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); pickFile(e.dataTransfer.files[0]) }}
      >
        <div className="dropzone-grid" />
        <div className="dropzone-icon-wrap"><UploadCloudIcon /></div>
        <p className="dropzone-text">Drag and drop, or <span style={{ color: 'var(--gold-from)', cursor: 'pointer' }}>browse</span></p>
        <p className="dropzone-exts mono">.mp4 · .avi · .mov · .mkv</p>
        <input
          ref={inputRef}
          type="file"
          accept=".mp4,.avi,.mov,.mkv"
          style={{ display: 'none' }}
          onChange={(e) => pickFile(e.target.files[0])}
        />
      </div>

      {picked && (
        <div className="file-selected">
          <div className="file-icon-tile"><FileVideoIcon /></div>
          <div className="file-info">
            <div className="file-name">{picked.name}</div>
            <div className="file-size">{fmt(picked.size)}</div>
          </div>
          <button className="file-remove" onClick={() => setPicked(null)} aria-label="Remove file">
            <XIcon />
          </button>
        </div>
      )}

      {error && (
        <div className="error-pill">
          <AlertIcon />
          {error}
        </div>
      )}

      <div className="upload-footer">
        <button className="btn btn-ghost" onClick={() => inputRef.current.click()}>Choose file</button>
        <button
          className="btn btn-primary"
          disabled={!picked || uploading}
          onClick={handleContinue}
        >
          <PlayIcon />
          {uploading ? 'Uploading…' : 'Continue'}
        </button>
      </div>
    </div>
  )
}
