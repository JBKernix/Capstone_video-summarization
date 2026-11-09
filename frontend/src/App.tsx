import { useCallback, useEffect, useState } from 'react'
import { api, type Session } from './api'
import { Notice } from './components/Notice'
import { DevApp } from './dev/DevApp'
import { LoginPage } from './pages/LoginPage'
import { UserApp } from './user/UserApp'

/** /dev 아래는 개발자용 화면, 그 외 모든 경로는 사용자용 화면입니다. */
function isDevPath() {
  const path = window.location.pathname
  return path === '/dev' || path.startsWith('/dev/')
}

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
  if (!session.authenticated) return <LoginPage onLogin={refresh} />

  return isDevPath() ? (
    <DevApp session={session} onSessionChange={refresh} />
  ) : (
    <UserApp session={session} onSessionChange={refresh} />
  )
}
