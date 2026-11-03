// 사용자용 화면에서 쓰는 쉬운 표현입니다. 서버의 단계·설정 이름(개발자용)을 그대로 보여 주지 않습니다.

export const FRIENDLY_STEPS: Record<number, { title: string; description: string }> = {
  1: { title: '강의 음성 분리', description: '영상에서 선생님 목소리를 꺼내고 있어요' },
  2: { title: '받아쓰기', description: '강의 내용을 글로 옮기고 있어요' },
  3: { title: '핵심 구간 찾기', description: '중요한 설명이 나오는 구간을 고르고 있어요' },
  4: { title: '중요 장면 캡처', description: '핵심 구간의 화면을 캡처하고 있어요' },
  5: { title: '판서·자막 읽기', description: '칠판, 슬라이드, 자막 글자를 읽고 있어요' },
  6: { title: '화면 내용 이해', description: '도표와 그림이 무엇을 설명하는지 살펴보고 있어요' },
  7: { title: '강의노트 완성', description: '말과 화면을 합쳐 핵심 노트를 정리하고 있어요' },
}

export const FRIENDLY_LEVELS: Record<string, { name: string; description: string }> = {
  simple: { name: '빠르게', description: '짧은 시간 안에 훑어보기' },
  standard: { name: '표준', description: '속도와 정확도의 균형 · 추천' },
  detailed: { name: '꼼꼼하게', description: '받아쓰기 정확도 우선 · 시간이 더 걸려요' },
}

export function formatClock(totalSeconds: number) {
  const seconds = Math.max(0, Math.floor(totalSeconds))
  const minutes = Math.floor(seconds / 60)
  return `${minutes}:${String(seconds % 60).padStart(2, '0')}`
}

export function formatDate(value: string | null | undefined) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('ko-KR', { year: 'numeric', month: 'long', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}
