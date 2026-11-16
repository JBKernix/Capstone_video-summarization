import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, type SummaryResult } from '../api'
import { Notice, PageTitle } from '../components/Notice'
import { SummaryView } from '../components/SummaryView'

export function ResultPage() {
  const { runId } = useParams()
  const [result, setResult] = useState<SummaryResult | null>(null)
  const [error, setError] = useState('')
  const [saveMessage, setSaveMessage] = useState<{ kind: 'success' | 'error'; text: string } | null>(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    setResult(null)
    setError('')
    api.get<SummaryResult>(`/api/runs/${runId}/result`).then(setResult, (err: Error) => setError(err.message))
  }, [runId])

  const save = async () => {
    setSaving(true)
    try {
      const { name } = await api.post<{ name: string }>(`/api/runs/${runId}/save`)
      setSaveMessage({ kind: 'success', text: `저장 완료: ${name} (저장된 요약 페이지에서 확인할 수 있습니다)` })
    } catch (err) {
      setSaveMessage({ kind: 'error', text: (err as Error).message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="page">
      <PageTitle sub="원본 영상과 최종 요약 결과를 확인하세요." />
      <p className="row" style={{ gap: '1.2rem' }}>
        <Link to="/result">📄 다른 분석 결과 보기</Link>
        <Link to="/history">📊 실행 시간과 처리량 확인</Link>
      </p>
      {error && (
        <>
          <Notice kind="warning">{error}</Notice>
          <Link className="button primary" to="/upload">
            영상 업로드로 이동
          </Link>
        </>
      )}
      {!result && !error && <p className="muted">결과를 불러오는 중입니다…</p>}
      {result && (
        <>
          <SummaryView result={result} />
          <div className="row" style={{ marginTop: '1.2rem' }}>
            <button onClick={save} disabled={saving}>
              💾 영상과 요약 결과 저장
            </button>
          </div>
          {saveMessage && <Notice kind={saveMessage.kind}>{saveMessage.text}</Notice>}
        </>
      )}
    </div>
  )
}
