// FastAPI 앱 서버(app/api/server.py) 호출 모음입니다.

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

// 서버의 CSRF 확인용 헤더입니다. 다른 사이트의 폼 전송은 이 헤더를 붙일 수 없습니다.
const CSRF_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' }

async function request<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: 'same-origin', headers: { ...CSRF_HEADERS } }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    init.headers = { ...CSRF_HEADERS, 'Content-Type': 'application/json' }
  }
  const response = await fetch(url, init)
  if (!response.ok) {
    let message = `요청에 실패했습니다 (HTTP ${response.status}).`
    try {
      const data = await response.json()
      if (typeof data.detail === 'string') message = data.detail
    } catch {
      // 본문이 JSON이 아니면 기본 문구를 씁니다.
    }
    if (response.status === 401) window.dispatchEvent(new Event('auth-required'))
    if (response.status === 403 && message.includes('개발자 모드')) window.dispatchEvent(new Event('dev-required'))
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}

export const api = {
  get: <T>(url: string) => request<T>('GET', url),
  post: <T>(url: string, body?: unknown) => request<T>('POST', url, body ?? {}),
  put: <T>(url: string, body: unknown) => request<T>('PUT', url, body),
  delete: <T>(url: string) => request<T>('DELETE', url),
}

/** 진행률을 받으며 업로드합니다(fetch는 업로드 진행률을 주지 않아 XHR을 씁니다). */
export function uploadWithProgress(file: File, onProgress: (percent: number) => void): Promise<Upload> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/uploads')
    xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest')
    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) onProgress((event.loaded / event.total) * 100)
    }
    xhr.onload = () => {
      let data: { detail?: string } & Partial<Upload> = {}
      try {
        data = JSON.parse(xhr.responseText)
      } catch {
        // 본문이 JSON이 아니면 기본 문구를 씁니다.
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(data as Upload)
      else {
        if (xhr.status === 401) window.dispatchEvent(new Event('auth-required'))
        reject(new ApiError(xhr.status, data.detail ?? `업로드에 실패했습니다 (HTTP ${xhr.status}).`))
      }
    }
    xhr.onerror = () => reject(new ApiError(0, '네트워크 오류로 업로드에 실패했습니다.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

/** 서버 응답을 파일로 내려받습니다. */
export async function downloadPost(url: string, body: unknown, filename: string) {
  const response = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { ...CSRF_HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) throw new ApiError(response.status, '다운로드에 실패했습니다.')
  saveBlob(await response.blob(), filename)
}

export function saveBlob(blob: Blob, filename: string) {
  const link = document.createElement('a')
  link.href = URL.createObjectURL(blob)
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(link.href), 1000)
}

// ---------------------------------------------------------------------------
// 응답 타입
// ---------------------------------------------------------------------------
export interface Session {
  required: boolean
  authenticated: boolean
  /** 개발자 모드(비밀번호 별도) 인증 여부입니다. */
  developer: boolean
}

export interface UserDefaults {
  analysis_backend: string
  local_model: string
}

export interface Option {
  id: string
  label: string
}

export interface SummaryLevel extends Option {
  stt_model: string
  caption: string
}

export interface StepInfo {
  step: number
  title: string
  description: string
}

export interface Options {
  summary_levels: SummaryLevel[]
  default_summary_level: string
  backends: Option[]
  local_models: Option[]
  default_local_model: string
  /** 사용자용 화면에서 시작한 분석에 쓰는 분석 방식(개발자가 지정)입니다. */
  user_defaults: UserDefaults
  claude_model: string
  backend_ready: boolean
  upload_limit_mb: number
  external: boolean
  video_extensions: string[]
  steps: StepInfo[]
}

export interface Upload {
  upload_id: string
  filename: string
  title: string
  source_key: string
}

export type StepState = 'done' | 'active-percent' | 'active-indeterminate' | 'error' | 'pending'

export interface RunStatus {
  run_id: string
  state: 'running' | 'success' | 'failed' | 'cancelled' | 'interrupted'
  returncode: number | null
  video_title: string | null
  uploaded_filename: string | null
  upload_id: string | null
  steps: (StepInfo & { state: StepState; percent: number | null; message: string })[]
  current: { step: number; title: string; percent: number | null; message: string } | null
  logs: string[]
}

export interface TimelineItem {
  type: 'item'
  index: number
  title: string
  start: number
  end: number | null
  label: string
  text: string
  /** 대표 화면 한 장(표/차트 화면 우선) */
  image_url: string | null
  /** 구간 안의 서로 다른 화면들(시간순). 표/차트 섹션이 아니면 빈 배열입니다. */
  frames: FrameRef[]
}

/** 구간에서 뽑은 화면 한 장과 그 시각입니다. */
export interface FrameRef {
  url: string
  time: number
  label: string
}

export type SummaryBlock =
  | { type: 'markdown'; text: string }
  | {
      type: 'items'
      heading: string
      show_images: boolean
      items: (TimelineItem | { type: 'markdown'; text: string })[]
    }

export interface StructuredSummary {
  title?: string
  main_topic?: string
  keywords?: string[]
  topics: { title?: string; timeline?: string; content?: string }[]
  conclusion?: string
}

/** 사용자용 강의노트(챕터 플레이어) 화면에 쓰는 요약 구조입니다. 타임라인 챕터가 없으면 null입니다. */
export interface NoteOutline {
  title: string | null
  /** 3줄 요약(최종 요약의 "핵심 주제") */
  key_points: string[]
  keywords: string[]
  chapters: NoteChapter[]
  /** 표/차트·수식·코드 등 화면 속 자료 */
  visuals: NoteVisual[]
  conclusion: string[]
  /** 핵심 용어와 정의(강의 노트 JSON 결과에만 있음) */
  terms: NoteTerm[]
  /** 강사가 "시험에 나온다", "중요하다" 등으로 강조한 내용(강의 노트 JSON 결과에만 있음) */
  emphasis: string[]
  /** 과제·시험·다음 수업 공지(강의 노트 JSON 결과에만 있음) */
  notices: string[]
  /** 위 분류에 들지 않은 마크다운 */
  extras: string[]
}

export interface NoteTerm {
  term: string
  definition: string
}

/** 화면 속 자료입니다. 강의 노트 JSON에서는 시간을 모르면 start가 null이고, kind에 자료 유형(표·수식 등)이 옵니다. */
export type NoteVisual = Omit<TimelineItem, 'start'> & { start: number | null; section: string; kind?: string }

export interface NoteChapter {
  index: number
  title: string
  /** 시간을 모르는 챕터는 null입니다(재생 버튼·챕터 막대에서 빠짐). */
  start: number | null
  end: number | null
  label: string
  points: string[]
  /** 화면 분석(VLM)에서 확인한 내용 */
  screen_notes: string[]
  thumb_url: string | null
  /** 챕터 구간 안의 서로 다른 화면들(시간순) */
  frames: FrameRef[]
}

export type SummaryContent =
  | { mode: 'blocks'; blocks: SummaryBlock[]; outline?: NoteOutline | null }
  | { mode: 'structured'; summary: StructuredSummary }
  | { mode: 'raw'; data: unknown }

export type SummaryResult = SummaryContent & {
  video_url: string | null
  title?: string | null
  saved_at?: string | null
}

export interface SavedItem {
  name: string
  title: string
  saved_at: string | null
}

export interface HistoryStage {
  step: number
  name: string
  status: string
  duration_seconds: number | null
  started_at: string | null
  finished_at: string | null
}

export interface HistoryRecord {
  run_id: string
  status: string
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  has_result?: boolean
  demo?: boolean
  error?: string | null
  input: { name?: string; duration_seconds?: number }
  settings: {
    summary_level?: string
    analysis_backend?: string
    preset_semantics?: string
    stt?: { model_size?: string }
    [key: string]: unknown
  }
  counts: Record<string, number | undefined>
  stages: HistoryStage[]
  environment?: unknown
  model_loading?: {
    summary: {
      model_load_seconds: number
      llm_load_seconds: number
      vlm_load_seconds: number
      model_load_count: number
      model_load_failed_count: number
      model_reuse_count: number
    }
    jobs: Record<string, { status?: string }>
  }
}

export interface ModelLoadRow {
  step: number
  model: string
  kind: string
  status: 'loaded' | 'reused' | 'failed'
  duration_seconds: number
  started_at: string | null
  job_id: string
}

export interface HistoryDetail {
  record: HistoryRecord
  model_load_rows: ModelLoadRow[]
  has_log: boolean
  log_tail: string
  log_truncated: boolean
}

export interface ModelCatalogueEntry {
  id: string
  label: string
  precision: string
  ready?: boolean
  runtime_ready?: boolean
  download?: { status?: string; error?: string }
}
