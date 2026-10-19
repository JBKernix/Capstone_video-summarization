import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api, uploadWithProgress, type ModelCatalogueEntry, type Options, type RunStatus, type Upload } from '../api'
import { Notice, PageTitle } from '../components/Notice'
import { StepTracker } from '../components/StepTracker'

const UPLOAD_KEY = 'current-upload'
const SETTINGS_KEY = 'analysis-settings'

interface Settings {
  analysis_backend: string
  local_model: string
  summary_level: string
}

function readStored<T>(storage: Storage, key: string): T | null {
  try {
    const value = storage.getItem(key)
    return value ? (JSON.parse(value) as T) : null
  } catch {
    return null
  }
}

function writeStored(storage: Storage, key: string, value: unknown) {
  try {
    if (value === null) storage.removeItem(key)
    else storage.setItem(key, JSON.stringify(value))
  } catch {
    // 개인정보 보호 모드 등에서 저장소를 못 써도 화면은 동작합니다.
  }
}

export function UploadPage() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const runId = searchParams.get('run')

  const [options, setOptions] = useState<Options | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [upload, setUpload] = useState<Upload | null>(() => readStored<Upload>(sessionStorage, UPLOAD_KEY))
  const [mode, setMode] = useState<'file' | 'youtube'>('file')
  const [error, setError] = useState('')
  const [status, setStatus] = useState<RunStatus | null>(null)
  const [otherRunning, setOtherRunning] = useState(false)
  const [starting, setStarting] = useState(false)

  const running = status?.state === 'running'

  useEffect(() => {
    api.get<Options>('/api/options').then((loaded) => {
      setOptions(loaded)
      const stored = readStored<Settings>(localStorage, SETTINGS_KEY)
      const valid = (list: { id: string }[], id: string | undefined, fallback: string) =>
        id && list.some((item) => item.id === id) ? id : fallback
      setSettings({
        analysis_backend: valid(loaded.backends, stored?.analysis_backend, 'local'),
        local_model: valid(loaded.local_models, stored?.local_model, loaded.default_local_model),
        summary_level: valid(loaded.summary_levels, stored?.summary_level, loaded.default_summary_level),
      })
    }, (err: Error) => setError(err.message))
  }, [])

  const changeSettings = (patch: Partial<Settings>) => {
    setSettings((current) => {
      const next = { ...(current as Settings), ...patch }
      writeStored(localStorage, SETTINGS_KEY, next)
      return next
    })
  }

  const changeUpload = useCallback((next: Upload | null) => {
    setUpload((previous) => {
      // 이 브라우저가 이전에 올린 영상만 정리합니다. 실행 중인 작업의 영상은 서버가 보존합니다.
      if (previous && previous.upload_id !== next?.upload_id) {
        api.delete(`/api/uploads/${previous.upload_id}`).catch(() => undefined)
      }
      writeStored(sessionStorage, UPLOAD_KEY, next)
      return next
    })
  }, [])

  // 실행 중이면 1초마다 진행 상황을 갱신합니다. URL의 run 값으로 새로고침 후에도 다시 연결합니다.
  useEffect(() => {
    if (!runId) {
      setStatus(null)
      return
    }
    let stopped = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await api.get<RunStatus>(`/api/runs/${runId}`)
        if (stopped) return
        setStatus(next)
        if (next.state === 'running') timer = window.setTimeout(poll, 1000)
        else if (next.state === 'success') navigate(`/result/${runId}`, { replace: true })
      } catch (err) {
        if (!stopped) setError((err as Error).message)
      }
    }
    void poll()
    return () => {
      stopped = true
      window.clearTimeout(timer)
    }
  }, [runId, navigate])

  // GPU 서버 한 대에서 전체 파이프라인은 한 번에 하나만 실행합니다.
  useEffect(() => {
    if (running) return
    let stopped = false
    const check = () =>
      api.get<{ run_id: string | null }>('/api/runs/active').then(
        (active) => !stopped && setOtherRunning(active.run_id !== null && active.run_id !== runId),
        () => undefined,
      )
    void check()
    const timer = window.setInterval(check, 5000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [running, runId])

  const start = async () => {
    if (!upload || !settings) return
    setError('')
    setStarting(true)
    try {
      const { run_id } = await api.post<{ run_id: string }>('/api/runs', { upload_id: upload.upload_id, ...settings })
      setSearchParams({ run: run_id })
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setStarting(false)
    }
  }

  const cancel = async () => {
    if (!runId) return
    try {
      await api.post(`/api/runs/${runId}/cancel`)
      setStatus(await api.get<RunStatus>(`/api/runs/${runId}`))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  return (
    <div className="page">
      <PageTitle sub="분석할 영상을 업로드한 뒤 영상 분석을 시작하세요." />
      <p>
        <Link to="/history">📊 실행 이력과 성능 지표 보기</Link>
      </p>
      {error && <Notice kind="error">{error}</Notice>}

      <div className="grid-3-2">
        <div className="card">
          <h2>🎥 영상 업로드</h2>
          <div className="segmented" style={{ marginBottom: '1rem' }}>
            <button className={mode === 'file' ? 'selected' : ''} onClick={() => setMode('file')} disabled={running}>
              파일 업로드
            </button>
            <button
              className={mode === 'youtube' ? 'selected' : ''}
              onClick={() => setMode('youtube')}
              disabled={running}
            >
              유튜브 링크
            </button>
          </div>
          {mode === 'file' ? (
            <FileUpload options={options} disabled={running} onUploaded={changeUpload} onError={setError} />
          ) : (
            <YoutubeUpload disabled={running} onUploaded={changeUpload} onError={setError} />
          )}
          {upload && !running && (
            <Notice kind="success">
              {upload.source_key.startsWith('youtube_') ? '유튜브 영상 다운로드' : '영상 업로드'}가 완료되었습니다.
              <br />
              파일명: {upload.filename}
            </Notice>
          )}
          {!upload && !running && <Notice kind="info">분석할 영상을 먼저 업로드하세요.</Notice>}
          {running && <Notice kind="info">분석이 진행 중일 때는 새 영상을 업로드할 수 없습니다.</Notice>}
        </div>

        <div className="card">
          {options && settings ? (
            <AnalysisOptions options={options} settings={settings} disabled={running} onChange={changeSettings} />
          ) : (
            <p className="muted">설정을 불러오는 중입니다…</p>
          )}
        </div>
      </div>

      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h2>🔎 분석 절차</h2>
        {options && <StepTracker steps={options.steps} status={status} />}
      </div>

      {otherRunning && !running && (
        <Notice kind="warning">다른 사용자의 영상 분석이 진행 중입니다. 완료된 뒤 분석을 시작할 수 있습니다.</Notice>
      )}
      <div style={{ maxWidth: 520, margin: '1.5rem auto 0' }}>
        <button
          className="primary big"
          onClick={start}
          disabled={!upload || running || starting || otherRunning || !options?.backend_ready}
        >
          ✨ 영상 분석 시작
        </button>
      </div>

      {status && <RunPanel status={status} onCancel={cancel} />}
    </div>
  )
}

function RunPanel({ status, onCancel }: { status: RunStatus; onCancel: () => void }) {
  if (status.state === 'running') {
    const current = status.current
    return (
      <div className="card" style={{ marginTop: '1.5rem' }}>
        <h2>영상 분석을 진행하고 있습니다.</h2>
        {current ? (
          <>
            <p>
              현재 단계: {current.step}/{status.steps.length} {current.title} — {current.message || current.title}
              {current.percent !== null && ` (${Math.round(current.percent)}%)`}
            </p>
            {current.percent !== null && (
              <div className="progress">
                <div style={{ width: `${Math.min(100, current.percent)}%` }} />
              </div>
            )}
          </>
        ) : (
          <p>파이프라인을 시작하는 중입니다...</p>
        )}
        {status.logs.length > 0 ? (
          <pre className="log">{status.logs.join('\n')}</pre>
        ) : (
          <Notice kind="info">분석 로그를 기다리는 중입니다.</Notice>
        )}
        <button className="danger" style={{ width: '100%' }} onClick={onCancel}>
          분석 중지
        </button>
      </div>
    )
  }
  if (status.state === 'success') return <Notice kind="success">분석 완료! 결과 화면으로 이동합니다.</Notice>

  return (
    <div className="card" style={{ marginTop: '1.5rem' }}>
      {status.state === 'cancelled' ? (
        <Notice kind="warning">분석이 중지되었습니다.</Notice>
      ) : (
        <Notice kind="error">분석 중 오류가 발생했습니다.</Notice>
      )}
      {status.logs.length > 0 ? (
        <>
          {status.state !== 'cancelled' && <p className="caption">마지막 실행 로그를 확인하세요.</p>}
          <pre className="log">{status.logs.join('\n')}</pre>
        </>
      ) : (
        status.state !== 'cancelled' && <p className="caption">표시할 수 있는 로그가 없습니다.</p>
      )}
    </div>
  )
}

function FileUpload({
  options,
  disabled,
  onUploaded,
  onError,
}: {
  options: Options | null
  disabled: boolean
  onUploaded: (upload: Upload) => void
  onError: (message: string) => void
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const [progress, setProgress] = useState<number | null>(null)
  const extensions = options?.video_extensions ?? ['.mp4', '.mov', '.avi']
  const limit = options?.upload_limit_mb

  const send = async (file: File | undefined) => {
    if (!file || disabled || progress !== null) return
    onError('')
    const suffix = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
    if (!extensions.includes(suffix)) return onError('지원 형식은 MP4, MOV, AVI입니다.')
    if (limit && file.size > limit * 1024 * 1024) return onError(`파일이 너무 큽니다. 업로드 한도는 ${limit}MB입니다.`)
    setProgress(0)
    try {
      onUploaded(await uploadWithProgress(file, setProgress))
    } catch (err) {
      onError((err as Error).message)
    } finally {
      setProgress(null)
      if (inputRef.current) inputRef.current.value = ''
    }
  }

  return (
    <>
      <div
        className={`dropzone${dragging ? ' dragging' : ''}${disabled ? ' disabled' : ''}`}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(event) => {
          event.preventDefault()
          if (!disabled) setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          void send(event.dataTransfer.files[0])
        }}
      >
        {progress === null ? (
          <>
            <strong>분석할 영상을 끌어다 놓거나 눌러서 선택하세요.</strong>
            <div className="caption">{extensions.join(', ').toUpperCase().replace(/\./g, '')}</div>
          </>
        ) : (
          <>
            <strong>업로드 중… {Math.round(progress)}%</strong>
            <div className="progress">
              <div style={{ width: `${progress}%` }} />
            </div>
            {progress >= 100 && <div className="caption">서버에서 영상 파일을 확인하는 중입니다…</div>}
          </>
        )}
      </div>
      <input
        ref={inputRef}
        type="file"
        accept={extensions.join(',')}
        hidden
        onChange={(event) => void send(event.target.files?.[0])}
      />
      {options?.external ? (
        <p className="caption">
          지원 형식: MP4, MOV, AVI · 외부 접속 업로드 한도: 파일당 {limit}MB (Cloudflare 요청 크기 제한). 더 큰 영상은
          유튜브 링크를 사용하거나 서버 PC에서 직접 업로드하세요.
        </p>
      ) : (
        <p className="caption">지원 형식: MP4, MOV, AVI</p>
      )}
    </>
  )
}

function YoutubeUpload({
  disabled,
  onUploaded,
  onError,
}: {
  disabled: boolean
  onUploaded: (upload: Upload) => void
  onError: (message: string) => void
}) {
  const [url, setUrl] = useState('')
  const [busy, setBusy] = useState(false)

  const download = async () => {
    onError('')
    setBusy(true)
    try {
      onUploaded(await api.post<Upload>('/api/uploads/youtube', { url }))
    } catch (err) {
      onError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="stack" style={{ gap: '0.6rem' }}>
      <input
        type="text"
        placeholder="https://www.youtube.com/watch?v=..."
        value={url}
        disabled={disabled || busy}
        onChange={(event) => setUrl(event.target.value)}
        onKeyDown={(event) => event.key === 'Enter' && url.trim() && void download()}
      />
      <div>
        <button onClick={download} disabled={disabled || busy || !url.trim()}>
          {busy ? '유튜브 영상을 다운로드하는 중입니다…' : '다운로드'}
        </button>
      </div>
    </div>
  )
}

function AnalysisOptions({
  options,
  settings,
  disabled,
  onChange,
}: {
  options: Options
  settings: Settings
  disabled: boolean
  onChange: (patch: Partial<Settings>) => void
}) {
  const level = options.summary_levels.find((item) => item.id === settings.summary_level)
  return (
    <>
      <h2>⚙️ 분석 설정</h2>
      <label className="field">분석 방식</label>
      <div className="segmented" style={{ margin: '0.4rem 0 0.8rem' }}>
        {options.backends.map((backend) => (
          <button
            key={backend.id}
            className={settings.analysis_backend === backend.id ? 'selected' : ''}
            disabled={disabled}
            onClick={() => onChange({ analysis_backend: backend.id })}
          >
            {backend.label}
          </button>
        ))}
      </div>

      {settings.analysis_backend === 'local' ? (
        <>
          <label className="field">
            로컬 분석 모델
            <select
              value={settings.local_model}
              disabled={disabled}
              onChange={(event) => onChange({ local_model: event.target.value })}
            >
              {options.local_models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                </option>
              ))}
            </select>
          </label>
          <p className="caption">
            {settings.local_model === 'legacy-qwen'
              ? '기존 조합 · 음성 요약 Qwen3 8B / 화면 분석 Qwen2.5-VL 7B · FP16'
              : '선택한 하나의 모델로 음성 요약·화면 분석·최종 요약을 처리합니다. 4090용 NF4 4비트 설정입니다.'}
          </p>
          <ModelStatus selected={settings.local_model} disabled={disabled} />
        </>
      ) : (
        <>
          <p className="caption">요약·화면 분석 모델: {options.claude_model}</p>
          <p className="caption">
            서버에 설정된 ANTHROPIC_API_KEY 환경변수를 자동으로 사용합니다. 분석 시작 전에 서버의 설정 여부를
            확인합니다.
          </p>
          <Notice kind="info">
            분석 서버가 인식한 음성 텍스트·OCR·추출 프레임을 Anthropic API로 전송합니다. API 사용 요금이 발생합니다.
          </Notice>
        </>
      )}
      <hr />
      <label className="field">Whisper 음성 인식</label>
      <div className="segmented" style={{ margin: '0.4rem 0' }}>
        {options.summary_levels.map((item) => (
          <button
            key={item.id}
            className={settings.summary_level === item.id ? 'selected' : ''}
            disabled={disabled}
            onClick={() => onChange({ summary_level: item.id })}
          >
            {item.label} · {item.stt_model}
          </button>
        ))}
      </div>
      {level && <p className="caption">{level.caption}</p>}
      <p className="caption">
        간단·기본·상세는 Whisper 크기만 바꿉니다. 세 옵션 모두 OCR·화면 분석·최종 통합을 수행하며 요약 생성 설정은
        같습니다.
      </p>
    </>
  )
}

const DOWNLOAD_STATUS: Record<string, string> = {
  queued: '다운로드 대기',
  downloading: '다운로드 중',
  failed: '다운로드 실패',
}

function ModelStatus({ selected, disabled }: { selected: string; disabled: boolean }) {
  const [catalogue, setCatalogue] = useState<ModelCatalogueEntry[]>([])
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const refresh = async () => {
    setError('')
    setLoading(true)
    try {
      setCatalogue((await api.get<{ models: ModelCatalogueEntry[] }>('/api/models')).models)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const selectedError = catalogue.find((model) => model.id === selected)?.download?.error
  return (
    <details className="topic">
      <summary>모델 설치 상태</summary>
      <p className="caption">GPU 서버에 미리 내려받은 모델의 설치 상태를 확인합니다.</p>
      <button className="small" onClick={refresh} disabled={disabled || loading} style={{ width: '100%' }}>
        설치 상태 확인 / 새로고침
      </button>
      {error && <Notice kind="error">{error}</Notice>}
      {selectedError && <Notice kind="error">{selectedError}</Notice>}
      {catalogue.length > 0 && (
        <div className="table-wrap" style={{ marginTop: '0.6rem' }}>
          <table>
            <thead>
              <tr>
                <th>모델</th>
                <th>정밀도</th>
                <th>상태</th>
              </tr>
            </thead>
            <tbody>
              {catalogue.map((model) => {
                let state =
                  DOWNLOAD_STATUS[model.download?.status ?? ''] ?? (model.ready ? '다운로드 완료' : '미설치')
                if (model.ready && model.runtime_ready === false) state = '가중치 완료 · 실행 환경 필요'
                return (
                  <tr key={model.id}>
                    <td>{model.label}</td>
                    <td>{model.precision.toUpperCase()}</td>
                    <td>{state}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
      <p className="caption">전체 다운로드: GPU 서버에서 python scripts/download_models.py --all</p>
      {selected === 'minicpm-v4.5' && (
        <Notice kind="info">MiniCPM은 서버에서 python scripts/setup_minicpm.py로 전용 환경을 먼저 설치하세요.</Notice>
      )}
      {selected === 'gemma4-12b' && (
        <p className="caption">
          접근 승인이 필요한 경우 Hugging Face에서 모델 사용 조건에 동의하고 서버 HF_TOKEN 환경변수를 설정하세요.
        </p>
      )}
    </details>
  )
}
