import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { Notice } from '../components/Notice'

export function LoginPage({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/api/login', { password })
      onLogin()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <form className="card login-box stack" style={{ gap: '1rem' }} onSubmit={submit}>
      <h2>🔒 로그인</h2>
      <label className="field">
        비밀번호
        <input type="password" autoFocus value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      {error && <Notice kind="error">{error}</Notice>}
      <button className="primary" type="submit" disabled={busy || !password}>
        입장
      </button>
    </form>
  )
}
