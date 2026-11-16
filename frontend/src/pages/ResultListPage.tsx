import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type HistoryRecord } from '../api'
import { Notice, PageTitle } from '../components/Notice'
import { localTime } from '../format'

/** 결과 화면을 다시 열 수 있는 완료된 분석 목록입니다(실행 산출물 보존 기간 안의 것만). */
export function ResultListPage() {
  const [records, setRecords] = useState<HistoryRecord[] | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.get<{ records: HistoryRecord[] }>('/api/history').then(
      (data) => setRecords(data.records.filter((record) => record.has_result)),
      (err: Error) => setError(err.message),
    )
  }, [])

  return (
    <div className="page">
      <PageTitle sub="완료된 분석의 결과 화면을 다시 확인하세요. 오래 보관하려면 결과 화면에서 저장하세요." />
      {error && <Notice kind="error">{error}</Notice>}
      {records === null && !error && <p className="muted">목록을 불러오는 중입니다…</p>}
      {records && records.length === 0 && (
        <>
          <Notice kind="info">
            다시 볼 수 있는 분석 결과가 없습니다. 분석 산출물은 보존 기간이 지나면 정리되며, 저장한 결과는 저장된 요약에서
            확인할 수 있습니다.
          </Notice>
          <div className="row">
            <Link className="button primary" to="/upload">
              영상 업로드로 이동
            </Link>
            <Link className="button" to="/saved">
              저장된 요약 보기
            </Link>
          </div>
        </>
      )}
      {records && records.length > 0 && (
        <div className="card">
          <h2>📄 분석 결과 목록</h2>
          <div className="saved-list" style={{ maxHeight: 'none' }}>
            {records.map((record) => (
              <Link className="button" key={record.run_id} to={`/result/${record.run_id}`} style={{ justifyContent: 'flex-start' }}>
                {record.input?.name ?? record.run_id} · {localTime(record.finished_at ?? record.started_at ?? record.created_at)}
              </Link>
            ))}
          </div>
          <p className="caption">
            분석 산출물은 보존 기간(기본 72시간)이 지나면 정리됩니다. 계속 보려면 결과 화면에서 "영상과 요약 결과 저장"을
            누르세요.
          </p>
        </div>
      )}
    </div>
  )
}
