import type { RunStatus, StepInfo } from '../api'

/** 분석 절차 7단계와 각 단계의 진행 상태를 표시합니다. */
export function StepTracker({ steps, status }: { steps: StepInfo[]; status: RunStatus | null }) {
  return (
    <div className="step-wrap">
      {steps.map((info) => {
        const step = status?.steps.find((item) => item.step === info.step)
        const state = step?.state ?? 'pending'
        let circleClass = 'step-circle'
        let circleStyle: React.CSSProperties | undefined
        let circleLabel = String(info.step)
        let descClass = 'step-desc'
        let descText = info.description

        if (state === 'done') {
          circleClass += ' step-done'
          circleLabel = '✓'
        } else if (state === 'error') {
          circleClass += ' step-error'
          circleLabel = '✕'
          descClass += ' step-error-text'
          descText = step?.message || '오류 발생'
        } else if (state === 'active-percent') {
          const percent = Math.round(step?.percent ?? 0)
          circleClass += ' step-active-percent'
          circleStyle = { background: `conic-gradient(#2563eb ${percent}%, #eaf2ff ${percent}%)` }
          circleLabel = `${percent}%`
          descClass += ' step-live'
          descText = step?.message || info.description
        } else if (state === 'active-indeterminate') {
          circleClass += ' step-active-indeterminate'
          descClass += ' step-live'
          descText = step?.message || info.description
        }

        return (
          <div className="step-item" key={info.step}>
            <div className={circleClass} style={circleStyle}>
              {circleLabel}
            </div>
            <div className="step-title">{info.title}</div>
            <div className={descClass}>{descText}</div>
          </div>
        )
      })}
    </div>
  )
}
