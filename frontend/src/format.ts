// 시간 표시는 한국 시간입니다.
const KST = new Intl.DateTimeFormat('ko-KR', {
  timeZone: 'Asia/Seoul',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: false,
})

export function localTime(value: string | null | undefined) {
  return value ? KST.format(new Date(value)) : '—'
}
