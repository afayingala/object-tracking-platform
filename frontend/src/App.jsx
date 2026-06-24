import { useState } from 'react'
import UploadPanel     from './components/UploadPanel'
import SelectPanel     from './components/SelectPanel'
import ConfigPanel     from './components/ConfigPanel'
import ProcessingPanel from './components/ProcessingPanel'
import ResultsView     from './components/ResultsView'
import './index.css'

const API = 'http://localhost:8000'

const STEPS     = ['Upload', 'Select', 'Configure', 'Process', 'Results']
const STEP_KEYS = ['upload', 'select',  'config',    'processing', 'results']

function CrosshairIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="8"/>
      <line x1="12" y1="2"  x2="12" y2="6"/>
      <line x1="12" y1="18" x2="12" y2="22"/>
      <line x1="2"  y1="12" x2="6"  y2="12"/>
      <line x1="18" y1="12" x2="22" y2="12"/>
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg className="stepper-check" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12"/>
    </svg>
  )
}

function Stepper({ current }) {
  const idx = STEP_KEYS.indexOf(current)
  return (
    <div className="stepper">
      {STEPS.map((label, i) => {
        const state = i < idx ? 'done' : i === idx ? 'active' : 'pending'
        return (
          <div key={label} style={{ display: 'contents' }}>
            <div className={`stepper-node ${state}`}>
              <div className={`stepper-circle ${state}`}>
                {state === 'done' ? <CheckIcon /> : i + 1}
              </div>
              <span className="stepper-label">{label}</span>
            </div>
            {i < STEPS.length - 1 && (
              <div className="stepper-line">
                <div className="stepper-line-fill" style={{ width: i < idx ? '100%' : '0%' }} />
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

export default function App() {
  const [videoId,       setVideoId]       = useState(null)
  const [filename,      setFilename]      = useState('')
  const [selectedBoxes, setSelectedBoxes] = useState([])   // 1–2 {x1,y1,x2,y2,class_name}
  const [jobId,         setJobId]         = useState(null)
  const [jobStatus,     setJobStatus]     = useState(null)
  const [progress,      setProgress]      = useState(0)
  const [summary,       setSummary]       = useState(null)
  const [jobError,      setJobError]      = useState('')
  const [config,        setConfig]        = useState({ confidence: 0.60, max_age: 90, min_hits: 3 })

  // Derive current step from state — no way for UI and data to diverge
  const step = !videoId              ? 'upload'
             : !selectedBoxes.length ? 'select'
             : !jobId                ? 'config'
             : jobStatus !== 'done'  ? 'processing'
             :                        'results'

  async function handleUpload(file) {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch(`${API}/api/upload`, { method: 'POST', body: form })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    setVideoId(data.video_id)
    setFilename(data.filename)
  }

  function handleSelect(boxes) {
    setSelectedBoxes(boxes)
  }

  async function handleProcess() {
    const res = await fetch(`${API}/api/process/${videoId}`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ ...config, selected_boxes: selectedBoxes }),
    })
    if (!res.ok) throw new Error(await res.text())
    const data = await res.json()
    setJobId(data.job_id)
    setJobStatus('queued')
    setProgress(0)
    setSummary(null)
    startWebSocket(data.job_id)
  }

  function startWebSocket(jid) {
    const ws = new WebSocket(`ws://localhost:8000/ws/${jid}`)
    ws.onmessage = (e) => {
      const msg = JSON.parse(e.data)
      if (msg.type === 'progress') setProgress(msg.progress)
      if (msg.type === 'status') {
        setJobStatus(msg.status)
        setProgress(msg.progress ?? 0)
        if (msg.summary) setSummary(msg.summary)
        if (msg.error)   setJobError(msg.error)
      }
      if (msg.type === 'done') {
        setJobStatus('done')
        setProgress(100)
        setSummary(msg.summary)
      }
    }
    ws.onerror = () => { setJobStatus('error'); setJobError('WebSocket connection failed.') }
  }

  function handleReset() {
    setVideoId(null);       setFilename('')
    setSelectedBoxes([]);   setJobId(null)
    setJobStatus(null);     setProgress(0)
    setSummary(null);       setJobError('')
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="header-inner">
          <div className="header-logo-tile"><CrosshairIcon /></div>
          <div className="header-brand">
            <span className="header-caption mono">Object detection and tracking</span>
            <span className="header-name">Tracking Studio</span>
          </div>
        </div>
      </header>

      <main className="app-main">
        <Stepper current={step} />

        {step === 'upload' && (
          <div className="panel-enter">
            <UploadPanel onUpload={handleUpload} />
          </div>
        )}
        {step === 'select' && (
          <div className="panel-enter">
            <SelectPanel
              videoId={videoId}
              api={API}
              onSelect={handleSelect}
              onBack={handleReset}
            />
          </div>
        )}
        {step === 'config' && (
          <div className="panel-enter">
            <ConfigPanel
              filename={filename}
              selectedBoxes={selectedBoxes}
              config={config}
              setConfig={setConfig}
              onProcess={handleProcess}
              onBack={() => setSelectedBoxes([])}
            />
          </div>
        )}
        {step === 'processing' && (
          <div className="panel-enter">
            <ProcessingPanel progress={progress} status={jobStatus} errorMsg={jobError} />
          </div>
        )}
        {step === 'results' && summary && (
          <div className="panel-enter">
            <ResultsView summary={summary} jobId={jobId} api={API} onReset={handleReset} />
          </div>
        )}
      </main>

      <footer className="app-footer">
        YOLOv8 · Appearance Re-ID · Focused instance tracking
      </footer>
    </div>
  )
}
