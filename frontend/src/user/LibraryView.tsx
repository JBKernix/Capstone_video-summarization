import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, type NoteCategory, type NoteClassification, type SavedItem } from '../api'
import { CATEGORIES, CATEGORY_LABELS, formatDate, noteCategory } from './labels'

type Filter = NoteCategory | 'ALL'

export function LibraryView() {
  const [items, setItems] = useState<SavedItem[] | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<Filter>('ALL')
  const [saving, setSaving] = useState('')

  useEffect(() => {
    api.get<{ items: SavedItem[] }>('/api/saved').then((data) => setItems(data.items), (err: Error) => setError(err.message))
  }, [])

  const changeCategory = async (name: string, category: NoteCategory) => {
    setSaving(name)
    setError('')
    try {
      const data = await api.put<{ classification: NoteClassification }>(
        `/api/saved/${encodeURIComponent(name)}/category`,
        { category },
      )
      setItems((current) =>
        (current ?? []).map((item) =>
          item.name === name ? { ...item, category: data.classification.category, classification: data.classification } : item,
        ),
      )
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setSaving('')
    }
  }

  const keyword = query.trim().toLowerCase()
  const counts = new Map<NoteCategory, number>()
  for (const item of items ?? []) {
    const category = noteCategory(item.category)
    counts.set(category, (counts.get(category) ?? 0) + 1)
  }
  const shown = (items ?? []).filter(
    (item) =>
      (filter === 'ALL' || noteCategory(item.category) === filter) && (!keyword || item.title.toLowerCase().includes(keyword)),
  )

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

      {items && items.length > 0 && (
        <div className="u-chips u-category-filter" role="tablist" aria-label="카테고리">
          {(['ALL', ...CATEGORIES] as Filter[]).map((value) => (
            <button
              key={value}
              role="tab"
              aria-selected={filter === value}
              className={`u-chip${filter === value ? ' on' : ''}`}
              onClick={() => setFilter(value)}
            >
              {value === 'ALL' ? '전체' : CATEGORY_LABELS[value]}
              <span className="u-chip-count">{value === 'ALL' ? items.length : (counts.get(value) ?? 0)}</span>
            </button>
          ))}
        </div>
      )}

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
      {items && items.length > 0 && shown.length === 0 && (
        <p className="u-muted">
          {keyword ? `‘${query}’와 맞는 노트가 없어요.` : `‘${CATEGORY_LABELS[filter as NoteCategory]}’ 노트가 없어요.`}
        </p>
      )}

      <div className="u-cards">
        {shown.map((item) => {
          const category = noteCategory(item.category)
          const review = item.classification?.status === 'NEEDS_REVIEW' || !item.classification
          return (
            <div key={item.name} className="u-note-card">
              <Link className="u-card" to={`/note/saved/${encodeURIComponent(item.name)}`}>
                <div className="u-card-thumb">📝</div>
                <div className="u-card-body">
                  <span className={`u-category-badge cat-${category}`} title={item.classification?.reason || undefined}>
                    {CATEGORY_LABELS[category]}
                  </span>
                  <strong>{item.title}</strong>
                  <span className="u-muted u-small">{formatDate(item.saved_at)}</span>
                </div>
              </Link>
              <label className="u-card-category">
                <span className="u-muted u-small">{review ? '분류 확인 필요' : '카테고리'}</span>
                <select
                  value={category}
                  disabled={saving === item.name}
                  onChange={(event) => changeCategory(item.name, event.target.value as NoteCategory)}
                  aria-label={`${item.title} 카테고리 변경`}
                >
                  {CATEGORIES.map((value) => (
                    <option key={value} value={value}>
                      {CATEGORY_LABELS[value]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )
        })}
      </div>
    </div>
  )
}
