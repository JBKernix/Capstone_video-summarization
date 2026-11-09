import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, type SavedItem, type SummaryResult } from '../api'
import { Notice, PageTitle } from '../components/Notice'
import { SummaryView } from '../components/SummaryView'

function formatSavedAt(value: string | null) {
  if (!value) return '시각 알수없음'
  return value.replace('T', ' ').slice(0, 19)
}

export function SavedPage() {
  const [items, setItems] = useState<SavedItem[] | null>(null)
  const [searchParams, setSearchParams] = useSearchParams()
  const [detail, setDetail] = useState<SummaryResult | null>(null)
  const [error, setError] = useState('')
  const [detailError, setDetailError] = useState('')
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [message, setMessage] = useState('')

  const selected = searchParams.get('item') ?? items?.[0]?.name ?? null

  const loadItems = () =>
    api.get<{ items: SavedItem[] }>('/api/saved').then((data) => setItems(data.items), (err: Error) => setError(err.message))

  useEffect(() => {
    void loadItems()
  }, [])

  useEffect(() => {
    setDetail(null)
    setDetailError('')
    setConfirmDelete(false)
    if (!selected) return
    api.get<SummaryResult>(`/api/saved/${encodeURIComponent(selected)}`).then(setDetail, (err: Error) =>
      setDetailError(err.message),
    )
  }, [selected])

  const remove = async () => {
    if (!selected) return
    try {
      await api.delete(`/api/saved/${encodeURIComponent(selected)}`)
      setMessage('삭제되었습니다.')
      setSearchParams({})
      await loadItems()
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const selectedItem = items?.find((item) => item.name === selected)

  return (
    <div className="page">
      <PageTitle sub="저장해 둔 영상과 요약 결과를 다시 확인하세요." />
      {error && <Notice kind="error">{error}</Notice>}
      {message && <Notice kind="success">{message}</Notice>}
      {items === null && !error && <p className="muted">목록을 불러오는 중입니다…</p>}
      {items && items.length === 0 && (
        <>
          <Notice kind="info">저장된 요약 결과가 없습니다.</Notice>
          <Link className="button primary" to="/upload">
            영상 업로드로 이동
          </Link>
        </>
      )}
      {items && items.length > 0 && (
        <>
          <div className="card">
            <h2>🗂️ 저장된 요약 목록</h2>
            <div className="saved-list">
              {items.map((item) => (
                <button
                  key={item.name}
                  className={item.name === selected ? 'selected' : ''}
                  onClick={() => {
                    setMessage('')
                    setSearchParams({ item: item.name })
                  }}
                >
                  {item.title} · {formatSavedAt(item.saved_at)}
                </button>
              ))}
            </div>
          </div>
          <div style={{ marginTop: '1.5rem' }}>
            {detailError && <Notice kind="warning">{detailError}</Notice>}
            {detail && <SummaryView result={detail} />}
          </div>
          {selectedItem && (
            <div style={{ marginTop: '1.2rem' }}>
              {!confirmDelete ? (
                <button className="danger" onClick={() => setConfirmDelete(true)}>
                  🗑️ 이 저장 결과 삭제
                </button>
              ) : (
                <>
                  <Notice kind="warning">
                    '{selectedItem.title}' 저장 결과를 삭제하시겠습니까? 이 작업은 되돌릴 수 없습니다.
                  </Notice>
                  <div className="row">
                    <button className="danger primary" onClick={remove}>
                      삭제 확인
                    </button>
                    <button onClick={() => setConfirmDelete(false)}>취소</button>
                  </div>
                </>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
