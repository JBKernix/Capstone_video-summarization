import { useCallback, useEffect, useState } from 'react'
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, type Session } from './api'
import { Notice } from './components/Notice'
import { HistoryPage } from './pages/HistoryPage'
import { HomePage } from './pages/HomePage'
import { LoginPage } from './pages/LoginPage'
import { ResultListPage } from './pages/ResultListPage'
import { ResultPage } from './pages/ResultPage'
import { SavedPage } from './pages/SavedPage'
import { UploadPage } from './pages/UploadPage'

export default function App() {
  const [session, setSession] = useState<Session | null>(null)
  const [error, setError] = useState('')

  const refresh = useCallback(() => {
    api.get<Session>('/api/session').then(setSession, (err: Error) => setError(err.message))
  }, [])

  useEffect(() => {
    refresh()
    // API가 401을 돌려주면(세션 만료 등) 로그인 화면으로 돌아갑니다.
    const onAuthRequired = () => setSession((current) => current && { ...current, authenticated: false })
    window.addEventListener('auth-required', onAuthRequired)
    return () => window.removeEventListener('auth-required', onAuthRequired)
  }, [refresh])

  if (error) {
    return (
      <div className="page">
        <Notice kind="error">서버에 연결할 수 없습니다: {error}</Notice>
      </div>
    )
  }
  if (!session) return null
  if (session.blocked) {
    return (
      <div className="page">
        <Notice kind="error">
          외부 접속용 비밀번호가 설정되지 않아 접속을 차단했습니다. 서버 관리자는 APP_PASSWORD를 설정한 뒤 서버를
          재시작하세요.
        </Notice>
      </div>
    )
  }
  if (!session.authenticated) return <LoginPage onLogin={refresh} />

  const logout = async () => {
    await api.post('/api/logout').catch(() => undefined)
    refresh()
  }

  return (
    <BrowserRouter>
      <header className="topbar">
        <Link className="brand" to="/">
          🎬 영상 요약
        </Link>
        <nav>
          <NavLink to="/upload">영상 업로드</NavLink>
          <NavLink to="/result">분석 결과</NavLink>
          <NavLink to="/saved">저장된 요약</NavLink>
          <NavLink to="/history">실행 이력</NavLink>
        </nav>
        <span className="spacer" />
        {session.required && (
          <button className="small" onClick={logout}>
            로그아웃
          </button>
        )}
      </header>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/upload" element={<UploadPage />} />
        <Route path="/result" element={<ResultListPage />} />
        <Route path="/result/:runId" element={<ResultPage />} />
        <Route path="/saved" element={<SavedPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
