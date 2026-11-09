import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type SavedItem } from '../api'
import { formatDate } from './labels'

export function LibraryView() {
  const [items, setItems] = useState<SavedItem[] | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')

  useEffect(() => {
    api.get<{ items: SavedItem[] }>('/api/saved').then((data) => setItems(data.items), (err: Error) => setError(err.message))
  }, [])

  const keyword = query.trim().toLowerCase()
  const shown = (items ?? []).filter((item) => !keyword || item.title.toLowerCase().includes(keyword))

  return (
    <div className="u-library">
      <div className="u-library-head">
        <div>
          <p className="u-eyebrow">내 강의노트</p>
          <h1>저장한 강의노트 {items ? <span className="u-count">{items.length}</span> : null}</h1>
        </div>
        {items && items.length > 0 && (
          <input
            type="search"
            className="u-search"
            placeholder="강의 제목으로 찾기"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        )}
      </div>

      {error && <div className="u-alert error">{error}</div>}
      {items === null && !error && <p className="u-muted">불러오는 중…</p>}
      {items && items.length === 0 && (
        <div className="u-panel u-center">
          <div className="u-big-icon">📚</div>
          <h2>아직 저장한 강의노트가 없어요</h2>
          <p className="u-muted">강의를 요약한 뒤 ‘내 강의노트에 저장’을 누르면 여기에 모여요.</p>
          <Link className="u-cta inline" to="/">
            첫 강의 요약하기
          </Link>
        </div>
      )}
      {items && items.length > 0 && shown.length === 0 && <p className="u-muted">‘{query}’와 맞는 노트가 없어요.</p>}

      <div className="u-cards">
        {shown.map((item) => (
          <Link key={item.name} className="u-card" to={`/note/saved/${encodeURIComponent(item.name)}`}>
            <div className="u-card-thumb">📝</div>
            <div className="u-card-body">
              <strong>{item.title}</strong>
              <span className="u-muted u-small">{formatDate(item.saved_at)}</span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  )
}
