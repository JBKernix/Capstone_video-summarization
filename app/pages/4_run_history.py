"""Read-only analysis dashboard backed by each execution's archived metrics."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.auth import require_login
from app.styles import apply_global_styles
from modules.common.run_history import DEFAULT_HISTORY_DIR, list_records, records_csv, run_directory, model_load_rows
from modules.llm.summary_levels import SUMMARY_LEVEL_LABELS
from modules.llm.backends import BACKEND_LABELS

STATUS = {"queued": "대기", "running": "진행 중", "success": "완료", "failed": "실패",
          "cancelled": "취소", "interrupted": "중단", "skipped": "생략"}


def duration(value):
    if value is None:
        return "—"
    minutes, seconds = divmod(float(value), 60)
    return f"{int(minutes)}분 {seconds:.1f}초" if minutes else f"{seconds:.2f}초"


def local_time(value):
    return datetime.fromisoformat(value).astimezone(timezone(timedelta(hours=9))).strftime("%m/%d %H:%M:%S") if value else "—"


st.set_page_config(page_title="실행 이력 · 영상 요약", page_icon="📊", layout="wide")
require_login()
apply_global_styles()
st.title("실행 이력")
st.caption("실행 시간과 처리량을 비교하고, 각 실행의 로그와 설정을 확인하세요. 시간 표시는 한국 시간입니다.")

top_left, top_right = st.columns([5, 1])
with top_right:
    st.button("새로고침", width="stretch")

records = list_records()
if not records:
    st.info("아직 저장된 실행 기록이 없습니다. 영상 분석을 시작하면 자동으로 기록됩니다.")
    st.page_link("pages/1_upload.py", label="영상 분석 시작", icon="🎬")
    st.stop()

if any(r.get("demo") for r in records):
    st.info("화면 검증용 예시 데이터가 포함되어 있습니다. 실제 모델 성능 측정값이 아닙니다.")

filters = st.columns([2, 1, 1])
query = filters[0].text_input("영상명 검색", placeholder="영상 이름으로 검색")
status_filter = filters[1].selectbox("실행 상태", ["전체", "완료", "실패", "취소", "진행 중", "대기", "중단"])
level_filter = filters[2].selectbox("Whisper 설정", ["전체", *SUMMARY_LEVEL_LABELS.values()])
filtered = [r for r in records if query.casefold() in r.get("input", {}).get("name", "").casefold()
            and (status_filter == "전체" or STATUS.get(r["status"]) == status_filter)
            and (level_filter == "전체" or SUMMARY_LEVEL_LABELS.get(r.get("settings", {}).get("summary_level")) == level_filter)]

finished = [r for r in filtered if r["status"] == "success"]
metrics = st.columns(4)
metrics[0].metric("실행 기록", f"{len(filtered)}회")
metrics[1].metric("완료 / 실패·취소", f"{len(finished)} / {sum(r['status'] in ('failed', 'cancelled', 'interrupted') for r in filtered)}")
times = [r["duration_seconds"] for r in finished if r.get("duration_seconds") is not None]
metrics[2].metric("평균 소요 · 완료 실행", duration(sum(times) / len(times) if times else None))
metrics[3].metric("추출 프레임 · 전체", f"{sum(r.get('counts', {}).get('frames_extracted', 0) for r in filtered):,}장")

if not filtered:
    st.info("조건에 맞는 실행 기록이 없습니다.")
    st.stop()

rows = [{"실행 시각": local_time(r.get("started_at") or r["created_at"]),
         "영상": r.get("input", {}).get("name"), "상태": STATUS.get(r["status"], r["status"]),
         "Whisper 설정": SUMMARY_LEVEL_LABELS.get(r.get("settings", {}).get("summary_level"), "—"),
         "분석 방식": BACKEND_LABELS.get(r.get("settings", {}).get("analysis_backend"), "기존 서버"),
         "소요 시간": duration(r.get("duration_seconds")),
         "추출 프레임": str(r.get("counts", {}).get("frames_extracted", "—")),
         "Whisper": r.get("settings", {}).get("stt", {}).get("model_size", "—"),
         "실행 ID": r["run_id"]} for r in filtered]
st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
st.download_button("실행 목록 CSV 다운로드", records_csv(filtered), "run_history.csv", "text/csv")

st.divider()
lookup = {r["run_id"]: r for r in filtered}
selected = st.selectbox("실행 상세", list(lookup), format_func=lambda key:
    f"{lookup[key].get('input', {}).get('name', key)} · {local_time(lookup[key].get('started_at') or lookup[key]['created_at'])} · {STATUS.get(lookup[key]['status'])}")
record = lookup[selected]
directory = run_directory(DEFAULT_HISTORY_DIR, selected)
if record.get("settings", {}).get("preset_semantics") != "whisper_only_v1":
    st.caption("이전 버전 기록입니다. 당시 간단·기본·상세는 Whisper 외에 분석 범위와 요약 설정도 달랐습니다.")
if record.get("demo"):
    st.caption("선택한 기록: 화면 검증용 예시")
if record.get("error"):
    st.warning(record["error"])
if record["status"] in ("running", "queued"):
    st.info("마지막 저장 상태입니다. 새로고침으로 갱신하세요. 강제 종료·전원 차단 시 진행 중 상태가 남을 수 있습니다.")

tabs = st.tabs(["단계별 시간", "처리량과 설정", "원본 로그"])
with tabs[0]:
    stages = record.get("stages", [])
    if stages:
        stage_rows = [{"단계": s["name"], "상태": STATUS.get(s["status"], s["status"]),
                       "소요 시간(초)": s.get("duration_seconds"),
                       "시작": local_time(s.get("started_at")), "종료": local_time(s.get("finished_at"))} for s in stages]
        chart_rows = [r for r in stage_rows if r["소요 시간(초)"] is not None and r["상태"] != "생략"]
        if chart_rows:
            import altair as alt
            chart = alt.Chart(pd.DataFrame(chart_rows)).mark_bar(color="#2563eb", cornerRadiusEnd=4).encode(
                x=alt.X("소요 시간(초):Q", title="소요 시간 (초)"),
                y=alt.Y("단계:N", sort=None, title=None),
                tooltip=["단계", "상태", alt.Tooltip("소요 시간(초):Q", format=".3f")],
            ).properties(height=230)
            st.altair_chart(chart, width="stretch")
        st.dataframe(pd.DataFrame(stage_rows), hide_index=True, width="stretch")
    else:
        st.info("아직 시작된 단계가 없습니다.")
    st.caption("전체 시간에는 준비·변환·기록 시간도 포함됩니다. 서버 호출 단계는 통신·대기·추론을 포함한 클라이언트 측 경과 시간입니다.")
    st.subheader("서버 모델 로딩")
    loading = record.get("model_loading")
    if loading is None:
        st.info("별도 로딩 기록이 없습니다. 이전 기록·구버전 서버 또는 Claude API 분석에는 로컬 LLM/VLM 로딩 지표가 없을 수 있습니다.")
    else:
        summary = loading["summary"]
        cols = st.columns(3)
        cols[0].metric("로딩 시간 합계", f"{summary['model_load_seconds']:.3f}초")
        cols[1].metric("LLM 로딩", f"{summary['llm_load_seconds']:.3f}초")
        cols[2].metric("VLM 로딩", f"{summary['vlm_load_seconds']:.3f}초")
        st.caption(f"로딩 성공 {summary['model_load_count']}회 · 실패 {summary['model_load_failed_count']}회 · 이미 로딩된 모델 재사용 {summary['model_reuse_count']}회")
        rows = model_load_rows(record)
        if rows:
            st.dataframe(pd.DataFrame([{
                "단계": {3: "STT 요약", 6: "VLM 요약", 7: "최종 요약"}.get(e["step"], str(e["step"])),
                "모델": e["model"], "종류": e["kind"].upper(),
                "상태": {"loaded": "로딩 완료", "reused": "재사용", "failed": "로딩 실패"}[e["status"]],
                "로딩 시간(초)": e["duration_seconds"], "시작": local_time(e.get("started_at")), "작업 ID": e["job_id"]
            } for e in rows]), hide_index=True, width="stretch")
        if any(job.get("status") not in ("completed", "failed") for job in loading["jobs"].values()):
            st.caption("아직 서버 작업이 완료되지 않았거나 연결이 끊겨, 마지막으로 수신한 계측값만 표시합니다.")
        st.caption("서버에서 토크나이저·프로세서 및 모델 로딩과 GPU 전송 완료까지 측정합니다. 실패한 로딩 시도도 합계에 포함하며 재사용은 0초입니다. 단계별 시간에 이미 포함된 값이므로 전체 시간에 다시 더하지 않습니다. Whisper·OCR 로딩과 모델 해제 시간은 이 항목에 포함하지 않습니다.")

with tabs[1]:
    counts = record.get("counts", {})
    labels = {"frames_extracted": "추출 프레임", "ocr_success": "OCR 성공 프레임", "ocr_failed": "OCR 실패 프레임",
              "vlm_frames": "VLM 반환 결과", "vlm_batches": "VLM 완료 배치", "stt_segments": "STT 구간",
              "api_calls": "Claude 완료 API 응답", "api_input_tokens": "Claude 입력 토큰", "api_output_tokens": "Claude 출력 토큰"}
    st.dataframe(pd.DataFrame([{"항목": label, "개수": counts.get(key)} for key, label in labels.items()]), hide_index=True, width="stretch")
    st.caption("빈 값은 해당 단계가 실행되지 않았거나 아직 계측되지 않았음을 뜻합니다.")
    st.json({"영상": record.get("input"), "실행 설정": record.get("settings"), "환경": record.get("environment")}, expanded=False)

with tabs[2]:
    log_path = directory / "process.log"
    if not log_path.exists():
        log_path = directory / "pipeline.log"
    if log_path.exists():
        log = log_path.read_bytes()
        st.download_button("원본 로그 다운로드", log, f"{selected}.log", "text/plain")
        st.code(log[-100_000:].decode("utf-8", errors="replace"), language="text")
        if len(log) > 100_000:
            st.caption("화면에는 마지막 100KB만 표시합니다. 전체 내용은 다운로드하세요.")
    else:
        st.info("아직 기록된 로그가 없습니다.")

st.download_button("상세 지표 JSON 다운로드", json.dumps(record, ensure_ascii=False, indent=2), f"{selected}.json", "application/json")
