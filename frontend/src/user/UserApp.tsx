import { useEffect, useState } from 'react'
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, type Session } from '../api'
import { DevPasswordForm } from '../components/DevPasswordForm'
import { HomeView } from './HomeView'
import { LibraryView } from './LibraryView'
import { NoteView } from './NoteView'
import { ProgressView } from './ProgressView'
import './user.css'

/** 일반 사용자용 화면입니다. 접속하면 기본으로 이 화면이 열립니다. */
export function UserApp({ session, onSessionChange }: { session: Session; onSessionChange: () => void }) {
  const [devDialog, setDevDialog] = useState(false)

  useEffect(() => {
    document.title = '핵심만PLZ · 강의 영상 핵심 요약'
  }, [])

  const openDevMode = () => {
    if (session.developer) window.location.href = '/dev'
    else setDevDialog(true)
  }
  const logout = async () => {
    await api.post('/api/logout').catch(() => undefined)
    onSessionChange()
  }

  return (
    <BrowserRouter>
      <div className="u-shell">
        <header className="u-header">
          <div className="u-header-inner">
            <Link className="u-logo" to="/">
              <Logo />
            </Link>
            <nav className="u-nav">
              <NavLink to="/" end>
                요약하기
              </NavLink>
              <NavLink to="/library">내 강의노트</NavLink>
            </nav>
            <span className="u-spacer" />
            {session.required && (
              <button className="u-ghost" onClick={logout}>
                로그아웃
              </button>
            )}
            <button className="u-ghost u-dev-button" onClick={openDevMode} title="개발자 모드">
              🛠️ <span>개발자</span>
            </button>
          </div>
        </header>

        <main className="u-main">
          <Routes>
            <Route path="/" element={<HomeView />} />
            <Route path="/summarize/:runId" element={<ProgressView />} />
            <Route path="/note/run/:runId" element={<NoteView source="run" />} />
            <Route path="/note/saved/:name" element={<NoteView source="saved" />} />
            <Route path="/library" element={<LibraryView />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>

        <footer className="u-footer">
          <Logo small /> · 멀티모달 강의 영상 요약 서비스 · 캡스톤디자인
        </footer>
      </div>

      {devDialog && (
        <div className="u-modal-backdrop" onClick={() => setDevDialog(false)}>
          <div className="u-modal" role="dialog" aria-modal="true" onClick={(event) => event.stopPropagation()}>
            <div className="u-modal-head">
              <h2>🛠️ 개발자 모드</h2>
              <button className="u-close" onClick={() => setDevDialog(false)} aria-label="닫기">
                ✕
              </button>
            </div>
            <p className="u-muted">분석 방식 선택, 단계별 로그, 실행 이력을 확인하는 개발자용 화면입니다.</p>
            <DevPasswordForm onSuccess={() => (window.location.href = '/dev')} />
          </div>
        </div>
      )}
    </BrowserRouter>
  )
}

export function Logo({ small = false }: { small?: boolean }) {
  return (
    <span className={`u-logo-text${small ? ' small' : ''}`}>
      <span className="u-mark">핵심만</span>
      <span className="u-plz">PLZ</span>
    </span>
  )
}
