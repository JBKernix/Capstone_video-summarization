import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { api, type SummaryResult } from '../api'
import { SummaryBody, type Seek } from '../components/SummaryView'
import { ChapterNote } from './ChapterNote'
import { formatDate } from './labels'

/** 강의노트 화면입니다. 방금 끝난 요약(run)과 저장해 둔 노트(saved)를 같은 모양으로 보여 줍니다. */
export function NoteView({ source }: { source: 'run' | 'saved' }) {
  const params = useParams()
  const navigate = useNavigate()
  const id = source === 'run' ? params.runId : params.name
  const videoRef = useRef<HTMLVideoElement>(null)
  const [result, setResult] = useState<SummaryResult | null>(null)
  const [error, setError] = useState('')
  const [savedName, setSavedName] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [confirmDelete, setConfirmDelete] = useState(false)

  useEffect(() => {
    setResult(null)
    setError('')
    const url = source === 'run' ? `/api/runs/${id}/result` : `/api/saved/${encodeURIComponent(id ?? '')}`
    api.get<SummaryResult>(url).then(setResult, (err: Error) => setError(err.message))
  }, [source, id])

  const seek: Seek = (seconds) => {
    const video = videoRef.current
    if (!video) return
    video.currentTime = seconds
    void video.play()
    if (window.matchMedia('(max-width: 960px)').matches) video.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  const save = async () => {
    setSaving(true)
    setMessage(null)
    try {
      const { name } = await api.post<{ name: string }>(`/api/runs/${id}/save`)
      setSavedName(name)
    } catch (err) {
      setMessage({ kind: 'error', text: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    try {
      await api.delete(`/api/saved/${encodeURIComponent(id ?? '')}`)
      navigate('/library', { replace: true })
    } catch (err) {
      setMessage({ kind: 'error', text: (err as Error).message })
    }
  }

  if (error) {
    return (
      <div className="u-narrow">
        <div className="u-panel u-center">
          <div className="u-big-icon">📭</div>
          <h2>강의노트를 불러오지 못했어요</h2>
          <p className="u-muted">{error}</p>
          <Link className="u-cta inline" to={source === 'saved' ? '/library' : '/'}>
            {source === 'saved' ? '내 강의노트로' : '새 강의 요약하기'}
          </Link>
        </div>
      </div>
    )
  }
  if (!result) return <div className="u-narrow u-muted u-center">강의노트를 불러오는 중…</div>

  const title =
    result.title ||
    (result.mode === 'structured' ? result.summary.title : null) ||
    (result.mode === 'blocks' ? result.outline?.title : null) ||
    '강의노트'

  return (
    <div className="u-note">
      <div className="u-note-head">
        <div>
          <p className="u-eyebrow">{source === 'run' ? '방금 완성된 강의노트' : '내 강의노트'}</p>
          <h1>{title}</h1>
          {result.saved_at && <p className="u-muted">{formatDate(result.saved_at)} 저장</p>}
        </div>
        <div className="u-note-actions">
          {source === 'run' &&
            (savedName ? (
              <Link className="u-ghost on" to={`/note/saved/${encodeURIComponent(savedName)}`}>
                ✓ 저장됨 · 노트함에서 보기
              </Link>
            ) : (
              <button className="u-ghost primary" onClick={save} disabled={saving}>
                {saving ? '저장 중…' : '📌 내 강의노트에 저장'}
              </button>
            ))}
          <button className="u-ghost" onClick={() => window.print()}>
            🖨️ 인쇄 · PDF
          </button>
          {source === 'saved' &&
            (!confirmDelete ? (
              <button className="u-ghost danger" onClick={() => setConfirmDelete(true)}>
                삭제
              </button>
            ) : (
              <>
                <button className="u-ghost danger" onClick={remove}>
                  정말 삭제
                </button>
                <button className="u-ghost" onClick={() => setConfirmDelete(false)}>
                  취소
                </button>
              </>
            ))}
        </div>
      </div>
      {message && <div className={`u-alert ${message.kind}`}>{message.text}</div>}

      {result.mode === 'blocks' && result.outline ? (
        <ChapterNote outline={result.outline} videoUrl={result.video_url} />
      ) : (
        <div className="u-note-grid">
          <aside className="u-note-video">
            {result.video_url ? (
              <video ref={videoRef} src={result.video_url} controls preload="metadata" />
            ) : (
              <div className="u-video-missing">원본 영상을 찾을 수 없어요.</div>
            )}
            <p className="u-muted u-small">
              노트의 <span className="u-time-sample">▶ 시간</span>을 누르면 그 장면부터 재생돼요.
            </p>
          </aside>
          <article className="u-note-body">
            <SummaryBody result={result} seek={seek} />
          </article>
        </div>
      )}
    </div>
  )
}
