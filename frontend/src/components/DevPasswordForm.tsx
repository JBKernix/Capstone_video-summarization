import { useState, type FormEvent } from 'react'
import { api } from '../api'
import { Notice } from './Notice'

/** 개발자 비밀번호 입력 폼입니다. 사용자 화면의 팝업과 /dev 입구 화면이 함께 씁니다. */
export function DevPasswordForm({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError('')
    try {
      await api.post('/api/dev/login', { password })
      onSuccess()
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  return (
    <form className="stack" style={{ gap: '0.8rem' }} onSubmit={submit}>
      <label className="field">
        개발자 비밀번호
        <input type="password" autoFocus value={password} onChange={(event) => setPassword(event.target.value)} />
      </label>
      {error && <Notice kind="error">{error}</Notice>}
      <button className="primary" type="submit" disabled={busy || !password}>
        개발자 모드로 입장
      </button>
    </form>
  )
}
