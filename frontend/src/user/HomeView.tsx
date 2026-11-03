import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { api, uploadWithProgress, type Options, type Upload } from '../api'
import { FRIENDLY_LEVELS } from './labels'

type Phase = 'idle' | 'downloading' | 'uploading' | 'starting'

const YOUTUBE_PATTERN = /^(https?:\/\/)?((www|m|music)\.)?(youtube\.com|youtu\.be)\//i

export function HomeView() {
  const navigate = useNavigate()
  const fileRef = useRef<HTMLInputElement>(null)
  const [options, setOptions] = useState<Options | null>(null)
  const [mode, setMode] = useState<'youtube' | 'file'>('youtube')
  const [url, setUrl] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [dragging, setDragging] = useState(false)
  const [level, setLevel] = useState('standard')
  const [phase, setPhase] = useState<Phase>('idle')
  const [uploadPercent, setUploadPercent] = useState(0)
  const [error, setError] = useState('')
  const [activeRun, setActiveRun] = useState<string | null>(null)

  useEffect(() => {
    api.get<Options>('/api/options').then(
      (loaded) => {
        setOptions(loaded)
        setLevel(loaded.default_summary_level)
      },
      (err: Error) => setError(err.message),
    )
  }, [])

  // GPU 서버 한 대에서 요약은 한 번에 하나만 실행합니다. 진행 중인 요약이 있으면 알려 줍니다.
  useEffect(() => {
    let stopped = false
    const check = () =>
      api.get<{ run_id: string | null }>('/api/runs/active').then(
        (active) => !stopped && setActiveRun(active.run_id),
        () => undefined,
      )
    void check()
    const timer = window.setInterval(check, 5000)
    return () => {
      stopped = true
      window.clearInterval(timer)
    }
  }, [])

  const extensions = options?.video_extensions ?? ['.mp4', '.mov', '.avi']
  const limit = options?.upload_limit_mb
  const busy = phase !== 'idle'
  const ready = mode === 'youtube' ? YOUTUBE_PATTERN.test(url.trim()) : file !== null
  const canSubmit = ready && !busy && !activeRun && options?.backend_ready !== false

  const pickFile = (picked: File | undefined) => {
    if (!picked || busy) return
    setError('')
    const suffix = picked.name.slice(picked.name.lastIndexOf('.')).toLowerCase()
    if (!extensions.includes(suffix)) return setError('MP4, MOV, AVI 영상만 올릴 수 있어요.')
    if (limit && picked.size > limit * 1024 * 1024)
      return setError(`파일이 너무 커요. ${limit}MB 이하의 영상을 올리거나 유튜브 링크를 사용해 주세요.`)
    setFile(picked)
  }

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!canSubmit) return
    setError('')
    let upload: Upload | null = null
    try {
      if (mode === 'youtube') {
        setPhase('downloading')
        upload = await api.post<Upload>('/api/uploads/youtube', { url: url.trim() })
      } else if (file) {
        setPhase('uploading')
        setUploadPercent(0)
        upload = await uploadWithProgress(file, setUploadPercent)
      }
      if (!upload) return
      setPhase('starting')
      const { run_id } = await api.post<{ run_id: string }>('/api/runs', {
        upload_id: upload.upload_id,
        summary_level: level,
      })
      navigate(`/summarize/${run_id}`)
    } catch (err) {
      // 영상은 받았지만 요약을 시작하지 못했다면 받은 영상을 정리합니다.
      if (upload) api.delete(`/api/uploads/${upload.upload_id}`).catch(() => undefined)
      setError((err as Error).message)
      setPhase('idle')
    }
  }

  let buttonText = '✨ 핵심만 뽑아주세요'
  if (phase === 'downloading') buttonText = '유튜브에서 강의 영상을 가져오는 중…'
  else if (phase === 'uploading') buttonText = `영상 올리는 중… ${Math.round(uploadPercent)}%`
  else if (phase === 'starting') buttonText = '요약을 시작하는 중…'

  return (
    <>
      <section className="u-hero">
        <p className="u-eyebrow">AI 강의 요약 서비스</p>
        <h1>
          50분 강의,
          <br />
          <span className="u-mark">핵심만</span> 5분 만에 읽어요
        </h1>
        <p className="u-lead">
          유튜브 강의 링크만 넣으면 선생님의 설명과 칠판·슬라이드 화면을 함께 읽고,
          <br className="u-br-wide" /> 시간대별 핵심 강의노트를 만들어 드려요.
        </p>

        <form className="u-input-card" onSubmit={submit}>
          <div className="u-tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'youtube'}
              className={mode === 'youtube' ? 'on' : ''}
              onClick={() => setMode('youtube')}
              disabled={busy}
            >
              ▶ 유튜브 링크
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === 'file'}
              className={mode === 'file' ? 'on' : ''}
              onClick={() => setMode('file')}
              disabled={busy}
            >
              📁 영상 파일
            </button>
          </div>

          {mode === 'youtube' ? (
            <div className="u-url-row">
              <input
                type="text"
                inputMode="url"
                placeholder="https://www.youtube.com/watch?v=…"
                value={url}
                disabled={busy}
                onChange={(event) => setUrl(event.target.value)}
                aria-label="유튜브 강의 링크"
              />
            </div>
          ) : (
            <div
              className={`u-drop${dragging ? ' dragging' : ''}${busy ? ' disabled' : ''}`}
              onClick={() => !busy && fileRef.current?.click()}
              onDragOver={(event) => {
                event.preventDefault()
                if (!busy) setDragging(true)
              }}
              onDragLeave={() => setDragging(false)}
              onDrop={(event) => {
                event.preventDefault()
                setDragging(false)
                pickFile(event.dataTransfer.files[0])
              }}
            >
              {file ? (
                <>
                  <strong>🎞️ {file.name}</strong>
                  <span className="u-muted">{(file.size / 1024 / 1024).toFixed(1)}MB · 눌러서 다른 영상 선택</span>
                </>
              ) : (
                <>
                  <strong>강의 영상을 끌어다 놓거나 눌러서 선택하세요</strong>
                  <span className="u-muted">
                    MP4 · MOV · AVI{limit ? ` · 최대 ${limit}MB` : ''}
                  </span>
                </>
              )}
              {phase === 'uploading' && (
                <div className="u-bar">
                  <div style={{ width: `${uploadPercent}%` }} />
                </div>
              )}
              <input
                ref={fileRef}
                type="file"
                accept={extensions.join(',')}
                hidden
                onChange={(event) => {
                  pickFile(event.target.files?.[0])
                  event.target.value = ''
                }}
              />
            </div>
          )}

          <div className="u-level">
            <span className="u-level-label">요약 방식</span>
            <div className="u-chips">
              {(options?.summary_levels ?? []).map((item) => {
                const text = FRIENDLY_LEVELS[item.id] ?? { name: item.label, description: '' }
                return (
                  <button
                    type="button"
                    key={item.id}
                    className={`u-chip${level === item.id ? ' on' : ''}`}
                    onClick={() => setLevel(item.id)}
                    disabled={busy}
                    title={text.description}
                  >
                    {text.name}
                  </button>
                )
              })}
            </div>
            <span className="u-muted u-level-desc">{FRIENDLY_LEVELS[level]?.description}</span>
          </div>

          <button className="u-cta" type="submit" disabled={!canSubmit}>
            {busy && <span className="u-spinner" />}
            {buttonText}
          </button>

          {error && <div className="u-alert error">{error}</div>}
          {activeRun && !busy && (
            <div className="u-alert info">
              지금 다른 강의를 요약하고 있어요. 끝나면 바로 시작할 수 있어요.{' '}
              <Link to={`/summarize/${activeRun}`}>진행 상황 보기 →</Link>
            </div>
          )}
          {options && !options.backend_ready && (
            <div className="u-alert error">요약 서버가 준비되지 않았어요. 관리자에게 문의해 주세요.</div>
          )}
          {mode === 'youtube' && (
            <p className="u-hint">EBS·KOCW·대학 공개강의 등 유튜브에 올라온 강의 링크를 붙여 넣으세요.</p>
          )}
        </form>
      </section>

      <section className="u-section">
        <h2 className="u-section-title">이렇게 정리해 드려요</h2>
        <div className="u-features">
          <Feature
            icon="🎙️"
            title="말로 한 설명까지"
            text="강의 음성을 받아써서 선생님이 강조한 개념과 예시를 놓치지 않아요."
          />
          <Feature
            icon="🧑‍🏫"
            title="칠판·슬라이드까지"
            text="화면 속 판서, 수식, 슬라이드 글자를 읽어 말과 함께 요약해요."
          />
          <Feature
            icon="⏱️"
            title="시간대별 노트로"
            text="핵심마다 시간이 붙어 있어 누르면 그 장면부터 바로 다시 볼 수 있어요."
          />
        </div>
      </section>

      <section className="u-section">
        <h2 className="u-section-title">사용 방법</h2>
        <ol className="u-how">
          <li>
            <b>1</b>
            <div>
              <strong>강의 링크 붙여넣기</strong>
              <span>유튜브 강의 주소나 영상 파일을 넣어요.</span>
            </div>
          </li>
          <li>
            <b>2</b>
            <div>
              <strong>AI가 강의 듣고 보기</strong>
              <span>음성과 화면을 함께 분석해요.</span>
            </div>
          </li>
          <li>
            <b>3</b>
            <div>
              <strong>핵심 노트로 복습</strong>
              <span>저장해 두고 언제든 다시 봐요.</span>
            </div>
          </li>
        </ol>
      </section>
    </>
  )
}

function Feature({ icon, title, text }: { icon: string; title: string; text: string }) {
  return (
    <div className="u-feature">
      <div className="u-feature-icon">{icon}</div>
      <h3>{title}</h3>
      <p>{text}</p>
    </div>
  )
}
