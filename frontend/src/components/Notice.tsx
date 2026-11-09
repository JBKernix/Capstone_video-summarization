import type { ReactNode } from 'react'

export function Notice({ kind, children }: { kind: 'info' | 'success' | 'warning' | 'error'; children: ReactNode }) {
  return <div className={`notice ${kind}`}>{children}</div>
}

export function PageTitle({ sub }: { sub: string }) {
  return (
    <>
      <h1 className="main-title">멀티모달 기반 영상 요약 시스템</h1>
      <p className="sub-title">{sub}</p>
    </>
  )
}
