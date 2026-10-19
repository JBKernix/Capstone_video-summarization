import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api, downloadPost, saveBlob, type HistoryDetail, type HistoryRecord, type Options } from '../api'
import { Notice } from '../components/Notice'
import { localTime } from '../format'

const STATUS: Record<string, string> = {
  queued: '대기',
  running: '진행 중',
  success: '완료',
  failed: '실패',
  cancelled: '취소',
  interrupted: '중단',
  skipped: '생략',
}
const STATUS_FILTERS = ['전체', '완료', '실패', '취소', '진행 중', '대기', '중단']
const STEP_NAMES: Record<number, string> = { 3: 'STT 요약', 6: 'VLM 요약', 7: '최종 요약' }
const LOAD_STATUS = { loaded: '로딩 완료', reused: '재사용', failed: '로딩 실패' }
const COUNT_LABELS: Record<string, string> = {
  frames_extracted: '추출 프레임',
  ocr_success: 'OCR 성공 프레임',
  ocr_failed: 'OCR 실패 프레임',
  vlm_frames: 'VLM 반환 결과',
  vlm_batches: 'VLM 완료 배치',
  stt_segments: 'STT 구간',
  api_calls: 'Claude 완료 API 응답',
  api_input_tokens: 'Claude 입력 토큰',
  api_output_tokens: 'Claude 출력 토큰',
}

function duration(value: number | null | undefined) {
  if (value === null || value === undefined) return '—'
  const minutes = Math.floor(value / 60)
  const seconds = value - minutes * 60
  return minutes ? `${minutes}분 ${seconds.toFixed(1)}초` : `${seconds.toFixed(2)}초`
}

export function HistoryPage() {
  const [records, setRecords] = useState<HistoryRecord[] | null>(null)
  const [options, setOptions] = useState<Options | null>(null)
  const [error, setError] = useState('')
  const [query, setQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('전체')
  const [levelFilter, setLevelFilter] = useState('전체')
  const [searchParams, setSearchParams] = useSearchParams()

  const levelLabels = useMemo(
    () => Object.fromEntries((options?.summary_levels ?? []).map((level) => [level.id, level.label])),
    [options],
  )
  const backendLabels = useMemo(
    () => Object.fromEntries((options?.backends ?? []).map((backend) => [backend.id, backend.label])),
    [options],
  )

  const load = () => {
    setError('')
    api.get<{ records: HistoryRecord[] }>('/api/history').then((data) => setRecords(data.records), (err: Error) =>
      setError(err.message),
    )
  }

  useEffect(() => {
    load()
    api.get<Options>('/api/options').then(setOptions, () => undefined)
  }, [])

  const filtered = useMemo(
    () =>
      (records ?? []).filter(
        (record) =>
          (record.input?.name ?? '').toLowerCase().includes(query.toLowerCase()) &&
          (statusFilter === '전체' || STATUS[record.status] === statusFilter) &&
          (levelFilter === '전체' || levelLabels[record.settings?.summary_level ?? ''] === levelFilter),
      ),
    [records, query, statusFilter, levelFilter, levelLabels],
  )

  const finished = filtered.filter((record) => record.status === 'success')
  const times = finished.map((record) => record.duration_seconds).filter((value): value is number => value !== null)
  const selectedId = searchParams.get('run') ?? filtered[0]?.run_id
  const selected = filtered.find((record) => record.run_id === selectedId) ?? filtered[0]

  return (
    <div className="page">
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1 className="main-title">실행 이력</h1>
        <button onClick={load}>새로고침</button>
      </div>
      <p className="sub-title">
        실행 시간과 처리량을 비교하고, 각 실행의 로그와 설정을 확인하세요. 시간 표시는 한국 시간입니다.
      </p>
      {error && <Notice kind="error">{error}</Notice>}
      {records === null && !error && <p className="muted">실행 기록을 불러오는 중입니다…</p>}
      {records && records.length === 0 && (
        <>
          <Notice kind="info">아직 저장된 실행 기록이 없습니다. 영상 분석을 시작하면 자동으로 기록됩니다.</Notice>
          <Link to="/upload">🎬 영상 분석 시작</Link>
        </>
      )}
      {records && records.length > 0 && (
        <div className="stack">
          {records.some((record) => record.demo) && (
            <Notice kind="info">화면 검증용 예시 데이터가 포함되어 있습니다. 실제 모델 성능 측정값이 아닙니다.</Notice>
          )}
          <div className="grid-3-2" style={{ gridTemplateColumns: '2fr 1fr 1fr' }}>
            <label className="field">
              영상명 검색
              <input
                type="search"
                placeholder="영상 이름으로 검색"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
              />
            </label>
            <label className="field">
              실행 상태
              <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
                {STATUS_FILTERS.map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
            <label className="field">
              Whisper 설정
              <select value={levelFilter} onChange={(event) => setLevelFilter(event.target.value)}>
                {['전체', ...Object.values(levelLabels)].map((item) => (
                  <option key={item}>{item}</option>
                ))}
              </select>
            </label>
          </div>

          <div className="metrics">
            <Metric label="실행 기록" value={`${filtered.length}회`} />
            <Metric
              label="완료 / 실패·취소"
              value={`${finished.length} / ${
                filtered.filter((record) => ['failed', 'cancelled', 'interrupted'].includes(record.status)).length
              }`}
            />
            <Metric
              label="평균 소요 · 완료 실행"
              value={duration(times.length ? times.reduce((a, b) => a + b, 0) / times.length : null)}
            />
            <Metric
              label="추출 프레임 · 전체"
              value={`${filtered
                .reduce((sum, record) => sum + (record.counts?.frames_extracted ?? 0), 0)
                .toLocaleString()}장`}
            />
          </div>

          {filtered.length === 0 ? (
            <Notice kind="info">조건에 맞는 실행 기록이 없습니다.</Notice>
          ) : (
            <>
              <div className="table-wrap" style={{ maxHeight: 420 }}>
                <table>
                  <thead>
                    <tr>
                      {['실행 시각', '영상', '상태', 'Whisper 설정', '분석 방식', '소요 시간', '추출 프레임', 'Whisper', '결과', '실행 ID'].map(
                        (header) => (
                          <th key={header}>{header}</th>
                        ),
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {filtered.map((record) => (
                      <tr
                        key={record.run_id}
                        className={`clickable${record.run_id === selected?.run_id ? ' selected' : ''}`}
                        onClick={() => setSearchParams({ run: record.run_id })}
                      >
                        <td>{localTime(record.started_at ?? record.created_at)}</td>
                        <td>{record.input?.name}</td>
                        <td>{STATUS[record.status] ?? record.status}</td>
                        <td>{levelLabels[record.settings?.summary_level ?? ''] ?? '—'}</td>
                        <td>{backendLabels[record.settings?.analysis_backend ?? ''] ?? '기존 서버'}</td>
                        <td>{duration(record.duration_seconds)}</td>
                        <td>{record.counts?.frames_extracted ?? '—'}</td>
                        <td>{record.settings?.stt?.model_size ?? '—'}</td>
                        <td>
                          {record.has_result ? (
                            <Link to={`/result/${record.run_id}`} onClick={(event) => event.stopPropagation()}>
                              보기
                            </Link>
                          ) : (
                            '—'
                          )}
                        </td>
                        <td className="muted">{record.run_id}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <button
                  onClick={() =>
                    downloadPost('/api/history/csv', { run_ids: filtered.map((r) => r.run_id) }, 'run_history.csv').catch(
                      (err: Error) => setError(err.message),
                    )
                  }
                >
                  실행 목록 CSV 다운로드
                </button>
              </div>
              {selected && <RunDetail key={selected.run_id} runId={selected.run_id} hasResult={!!selected.has_result} />}
            </>
          )}
        </div>
      )}
    </div>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="metric">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  )
}

function RunDetail({ runId, hasResult }: { runId: string; hasResult: boolean }) {
  const [detail, setDetail] = useState<HistoryDetail | null>(null)
  const [error, setError] = useState('')
  const [tab, setTab] = useState(0)

  useEffect(() => {
    api.get<HistoryDetail>(`/api/history/${runId}`).then(setDetail, (err: Error) => setError(err.message))
  }, [runId])

  if (error) return <Notice kind="error">{error}</Notice>
  if (!detail) return <p className="muted">실행 상세를 불러오는 중입니다…</p>
  const { record } = detail

  return (
    <div className="card">
      <h2>
        실행 상세 · {record.input?.name ?? runId} · {localTime(record.started_at ?? record.created_at)} ·{' '}
        {STATUS[record.status]}
      </h2>
      {record.settings?.preset_semantics !== 'whisper_only_v1' && (
        <p className="caption">
          이전 버전 기록입니다. 당시 간단·기본·상세는 Whisper 외에 분석 범위와 요약 설정도 달랐습니다.
        </p>
      )}
      {hasResult && (
        <p>
          <Link className="button primary" to={`/result/${runId}`}>
            📄 결과 화면 보기
          </Link>
        </p>
      )}
      {record.demo && <p className="caption">선택한 기록: 화면 검증용 예시</p>}
      {record.error && <Notice kind="warning">{record.error}</Notice>}
      {['running', 'queued'].includes(record.status) && (
        <Notice kind="info">
          마지막 저장 상태입니다. 새로고침으로 갱신하세요. 강제 종료·전원 차단 시 진행 중 상태가 남을 수 있습니다.
        </Notice>
      )}

      <div className="tabs">
        {['단계별 시간', '처리량과 설정', '원본 로그'].map((label, index) => (
          <button key={label} className={tab === index ? 'selected' : ''} onClick={() => setTab(index)}>
            {label}
          </button>
        ))}
      </div>
      {tab === 0 && <StageTimes detail={detail} />}
      {tab === 1 && <Counts record={record} />}
      {tab === 2 && <RawLog detail={detail} runId={runId} />}

      <hr />
      <button
        onClick={() =>
          saveBlob(new Blob([JSON.stringify(record, null, 2)], { type: 'application/json' }), `${runId}.json`)
        }
      >
        상세 지표 JSON 다운로드
      </button>
    </div>
  )
}

function StageTimes({ detail }: { detail: HistoryDetail }) {
  const stages = detail.record.stages ?? []
  const chartRows = stages.filter((stage) => stage.duration_seconds !== null && stage.status !== 'skipped')
  const max = Math.max(...chartRows.map((stage) => stage.duration_seconds ?? 0), 0.001)
  const loading = detail.record.model_loading

  return (
    <>
      {stages.length === 0 ? (
        <Notice kind="info">아직 시작된 단계가 없습니다.</Notice>
      ) : (
        <>
          {chartRows.length > 0 && (
            <div className="bar-chart">
              {chartRows.map((stage) => (
                <div className="bar-row" key={stage.step} title={`${stage.name} · ${STATUS[stage.status]}`}>
                  <span>{stage.name}</span>
                  <div className="bar" style={{ width: `${((stage.duration_seconds ?? 0) / max) * 100}%` }} />
                  <span className="value">{(stage.duration_seconds ?? 0).toFixed(3)}초</span>
                </div>
              ))}
            </div>
          )}
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>단계</th>
                  <th>상태</th>
                  <th>소요 시간(초)</th>
                  <th>시작</th>
                  <th>종료</th>
                </tr>
              </thead>
              <tbody>
                {stages.map((stage) => (
                  <tr key={stage.step}>
                    <td>{stage.name}</td>
                    <td>{STATUS[stage.status] ?? stage.status}</td>
                    <td>{stage.duration_seconds?.toFixed(3) ?? '—'}</td>
                    <td>{localTime(stage.started_at)}</td>
                    <td>{localTime(stage.finished_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      <p className="caption">
        전체 시간에는 준비·변환·기록 시간도 포함됩니다. 서버 호출 단계는 통신·대기·추론을 포함한 클라이언트 측 경과
        시간입니다.
      </p>

      <h3>서버 모델 로딩</h3>
      {!loading ? (
        <Notice kind="info">
          별도 로딩 기록이 없습니다. 이전 기록·구버전 서버 또는 Claude API 분석에는 로컬 LLM/VLM 로딩 지표가 없을 수
          있습니다.
        </Notice>
      ) : (
        <>
          <div className="metrics" style={{ gridTemplateColumns: 'repeat(3, 1fr)' }}>
            <Metric label="로딩 시간 합계" value={`${loading.summary.model_load_seconds.toFixed(3)}초`} />
            <Metric label="LLM 로딩" value={`${loading.summary.llm_load_seconds.toFixed(3)}초`} />
            <Metric label="VLM 로딩" value={`${loading.summary.vlm_load_seconds.toFixed(3)}초`} />
          </div>
          <p className="caption">
            로딩 성공 {loading.summary.model_load_count}회 · 실패 {loading.summary.model_load_failed_count}회 · 이미
            로딩된 모델 재사용 {loading.summary.model_reuse_count}회
          </p>
          {detail.model_load_rows.length > 0 && (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    {['단계', '모델', '종류', '상태', '로딩 시간(초)', '시작', '작업 ID'].map((header) => (
                      <th key={header}>{header}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detail.model_load_rows.map((row, index) => (
                    <tr key={index}>
                      <td>{STEP_NAMES[row.step] ?? row.step}</td>
                      <td>{row.model}</td>
                      <td>{row.kind.toUpperCase()}</td>
                      <td>{LOAD_STATUS[row.status]}</td>
                      <td>{row.duration_seconds}</td>
                      <td>{localTime(row.started_at)}</td>
                      <td className="muted">{row.job_id}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {Object.values(loading.jobs).some((job) => !['completed', 'failed'].includes(job.status ?? '')) && (
            <p className="caption">
              아직 서버 작업이 완료되지 않았거나 연결이 끊겨, 마지막으로 수신한 계측값만 표시합니다.
            </p>
          )}
          <p className="caption">
            서버에서 토크나이저·프로세서 및 모델 로딩과 GPU 전송 완료까지 측정합니다. 실패한 로딩 시도도 합계에
            포함하며 재사용은 0초입니다. 단계별 시간에 이미 포함된 값이므로 전체 시간에 다시 더하지 않습니다.
            Whisper·OCR 로딩과 모델 해제 시간은 이 항목에 포함하지 않습니다.
          </p>
        </>
      )}
    </>
  )
}

function Counts({ record }: { record: HistoryRecord }) {
  return (
    <>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>항목</th>
              <th>개수</th>
            </tr>
          </thead>
          <tbody>
            {Object.entries(COUNT_LABELS).map(([key, label]) => (
              <tr key={key}>
                <td>{label}</td>
                <td>{record.counts?.[key] ?? ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="caption">빈 값은 해당 단계가 실행되지 않았거나 아직 계측되지 않았음을 뜻합니다.</p>
      <details className="topic">
        <summary>영상 · 실행 설정 · 환경</summary>
        <pre className="log">
          {JSON.stringify(
            { 영상: record.input, '실행 설정': record.settings, 환경: record.environment },
            null,
            2,
          )}
        </pre>
      </details>
    </>
  )
}

function RawLog({ detail, runId }: { detail: HistoryDetail; runId: string }) {
  if (!detail.has_log) return <Notice kind="info">아직 기록된 로그가 없습니다.</Notice>
  return (
    <>
      <a className="button small" href={`/api/history/${runId}/log`} download={`${runId}.log`}>
        원본 로그 다운로드
      </a>
      <pre className="log">{detail.log_tail}</pre>
      {detail.log_truncated && (
        <p className="caption">화면에는 마지막 100KB만 표시합니다. 전체 내용은 다운로드하세요.</p>
      )}
    </>
  )
}
