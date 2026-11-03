import { useEffect, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type RunStatus } from '../api'
import { FRIENDLY_STEPS, formatClock } from './labels'

/** 전체 진행률(%)입니다. 끝난 단계 + 현재 단계의 진행분을 7단계 기준으로 환산합니다. */
function overallPercent(status: RunStatus) {
  const total = status.steps.length || 1
  let progress = 0
  for (const step of status.steps) {
    if (step.state === 'done') progress += 1
    else if (step.state === 'active-percent') progress += Math.min(100, step.percent ?? 0) / 100
    else if (step.state === 'active-indeterminate') progress += 0.3
  }
  return Math.min(99, Math.round((progress / total) * 100))
}

export function ProgressView() {
  const { runId } = useParams()
  const navigate = useNavigate()
  const [status, setStatus] = useState<RunStatus | null>(null)
  const [error, setError] = useState('')
  const [elapsed, setElapsed] = useState(0)
  const [confirmCancel, setConfirmCancel] = useState(false)

  useEffect(() => {
    let stopped = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const next = await api.get<RunStatus>(`/api/runs/${runId}`)
        if (stopped) return
        setStatus(next)
        if (next.state === 'running') timer = window.setTimeout(poll, 1500)
        else if (next.state === 'success') navigate(`/note/run/${runId}`, { replace: true })
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

  const running = status?.state === 'running'
  useEffect(() => {
    if (!running) return
    const started = Date.now() - elapsed * 1000
    const timer = window.setInterval(() => setElapsed((Date.now() - started) / 1000), 1000)
    return () => window.clearInterval(timer)
    // 경과 시간은 실행 중일 때만 셉니다.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [running])

  const cancel = async () => {
    try {
      await api.post(`/api/runs/${runId}/cancel`)
      setStatus(await api.get<RunStatus>(`/api/runs/${runId}`))
    } catch (err) {
      setError((err as Error).message)
    }
  }

  if (error && !status) {
    return (
      <div className="u-narrow">
        <div className="u-panel u-center">
          <div className="u-big-icon">🔍</div>
          <h2>요약 작업을 찾을 수 없어요</h2>
          <p className="u-muted">{error}</p>
          <Link className="u-cta inline" to="/">
            새 강의 요약하기
          </Link>
        </div>
      </div>
    )
  }
  if (!status) return <div className="u-narrow u-muted u-center">불러오는 중…</div>

  if (!running && status.state !== 'success') {
    const cancelled = status.state === 'cancelled'
    return (
      <div className="u-narrow">
        <div className="u-panel u-center">
          <div className="u-big-icon">{cancelled ? '⏹️' : '😢'}</div>
          <h2>{cancelled ? '요약을 취소했어요' : '요약 중 문제가 생겼어요'}</h2>
          <p className="u-muted">
            {cancelled
              ? '언제든 다시 요약을 시작할 수 있어요.'
              : '영상 길이나 형식, 서버 상태 때문에 실패했을 수 있어요. 잠시 후 다시 시도해 주세요.'}
          </p>
          <Link className="u-cta inline" to="/">
            다시 요약하기
          </Link>
        </div>
      </div>
    )
  }

  const percent = status.state === 'success' ? 100 : overallPercent(status)
  const current = status.current
  const currentFriendly = current ? FRIENDLY_STEPS[current.step] : null

  return (
    <div className="u-narrow">
      <div className="u-panel">
        <p className="u-eyebrow">핵심만 뽑는 중</p>
        <h2 className="u-progress-title">{status.video_title || '강의 영상'}</h2>

        <div className="u-progress-head">
          <span className="u-progress-percent">{percent}%</span>
          <span className="u-muted">경과 {formatClock(elapsed)}</span>
        </div>
        <div className="u-bar big">
          <div style={{ width: `${percent}%` }} />
        </div>
        <p className="u-now">
          {currentFriendly ? (
            <>
              <span className="u-pulse" /> {currentFriendly.description}
            </>
          ) : (
            '요약을 준비하고 있어요…'
          )}
        </p>

        <ol className="u-steps">
          {status.steps.map((step) => {
            const friendly = FRIENDLY_STEPS[step.step] ?? { title: step.title, description: step.description }
            const state = step.state === 'done' ? 'done' : step.state.startsWith('active') ? 'active' : 'pending'
            return (
              <li key={step.step} className={`u-step ${state}`}>
                <span className="u-step-dot">
                  {state === 'done' ? '✓' : state === 'active' ? <span className="u-spinner dark" /> : step.step}
                </span>
                <span className="u-step-title">{friendly.title}</span>
                {state === 'active' && step.percent !== null && (
                  <span className="u-step-pct">{Math.round(step.percent)}%</span>
                )}
              </li>
            )
          })}
        </ol>

        <p className="u-muted u-small">
          강의 길이에 따라 몇 분에서 수십 분까지 걸려요. 요약이 끝나면 이 화면에서 바로 강의노트를 보여 드려요.
        </p>
        {error && <div className="u-alert error">{error}</div>}

        <div className="u-cancel-row">
          {!confirmCancel ? (
            <button className="u-ghost" onClick={() => setConfirmCancel(true)}>
              요약 취소
            </button>
          ) : (
            <>
              <span>정말 취소할까요?</span>
              <button className="u-ghost danger" onClick={cancel}>
                네, 취소할게요
              </button>
              <button className="u-ghost" onClick={() => setConfirmCancel(false)}>
                계속 진행
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
