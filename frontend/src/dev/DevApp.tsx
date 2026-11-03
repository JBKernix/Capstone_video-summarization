import { useEffect, useState } from 'react'
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes } from 'react-router-dom'
import { api, type Session } from '../api'
import { DevPasswordForm } from '../components/DevPasswordForm'
import { HistoryPage } from '../pages/HistoryPage'
import { HomePage } from '../pages/HomePage'
import { ResultListPage } from '../pages/ResultListPage'
import { ResultPage } from '../pages/ResultPage'
import { SavedPage } from '../pages/SavedPage'
import { UploadPage } from '../pages/UploadPage'

/** 개발자용 화면(/dev 아래)입니다. 개발자 비밀번호로 인증해야 들어올 수 있습니다. */
export function DevApp({ session, onSessionChange }: { session: Session; onSessionChange: () => void }) {
  const [developer, setDeveloper] = useState(session.developer)

  useEffect(() => setDeveloper(session.developer), [session.developer])
  useEffect(() => {
    // 개발자 쿠키가 만료되면 API가 403을 돌려주고, 다시 비밀번호를 묻습니다.
    const onDevRequired = () => setDeveloper(false)
    window.addEventListener('dev-required', onDevRequired)
    return () => window.removeEventListener('dev-required', onDevRequired)
  }, [])

  if (!developer) {
    return (
      <div className="card login-box stack" style={{ gap: '1rem' }}>
        <h2>🛠️ 개발자 모드</h2>
        <p className="caption" style={{ margin: 0 }}>
          분석 방식 선택, 실행 이력, 로그 등 개발자용 화면입니다. 개발자 비밀번호를 입력하세요.
        </p>
        <DevPasswordForm onSuccess={onSessionChange} />
        <a href="/">← 사용자 화면으로 돌아가기</a>
      </div>
    )
  }

  const exitDevMode = async () => {
    await api.post('/api/dev/logout').catch(() => undefined)
    window.location.href = '/'
  }
  const logout = async () => {
    await api.post('/api/logout').catch(() => undefined)
    window.location.href = '/'
  }

  return (
    <BrowserRouter basename="/dev">
      <header className="topbar">
        <Link className="brand" to="/">
          🛠️ 핵심만PLZ <span className="dev-badge">개발자 모드</span>
        </Link>
        <nav>
          <NavLink to="/upload">영상 업로드</NavLink>
          <NavLink to="/result">분석 결과</NavLink>
          <NavLink to="/saved">저장된 요약</NavLink>
          <NavLink to="/history">실행 이력</NavLink>
        </nav>
        <span className="spacer" />
        <a className="button small" href="/">
          사용자 화면
        </a>
        <button className="small" onClick={exitDevMode}>
          개발자 모드 종료
        </button>
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
