# 데이터 형식

파이프라인은 `runs/` 아래에 단계별 JSON/TXT 결과를 저장합니다. 이 문서는 주요 산출물의 구조를 정리합니다.

## 프레임 메타데이터

경로: `runs/metadata/frame_metadata.json`

```json
[
  {
    "frame_id": 0,
    "timestamp": 12.5,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "interval"
  }
]
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `frame_id` | number | 추출 순서 |
| `timestamp` | number | 영상 내 시점, 초 단위 |
| `image_path` | string | 프레임 이미지 경로 |
| `sampling_method` | string | `interval` 또는 `scene_change` |

## STT 결과

경로: `runs/stt/stt_result.json`

```json
{
  "language": "ko",
  "segment_count": 2,
  "segments": [
    {
      "segment_id": 0,
      "start": 0.0,
      "end": 3.5,
      "text": "인식된 문장"
    }
  ],
  "full_text": "인식된 전체 텍스트"
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `language` | string | Whisper가 반환한 언어 코드 |
| `segment_count` | number | 유효 segment 개수 |
| `segments` | array | 시간 구간별 STT 결과 |
| `full_text` | string | segment 텍스트를 합친 전체 텍스트 |

TXT 출력은 `runs/stt/stt_result.txt`에 저장됩니다. `--stt-timestamps`를 사용하면 각 줄에 시작/종료 시간이 포함됩니다.

## STT 요약 결과

경로:

```text
runs/llm/stt_summary.txt
runs/llm/stt_summary_result.json
```

```json
{
  "source": {
    "language": "ko",
    "duration_sec": null,
    "segment_count": 10
  },
  "summary": "STT 기반 요약",
  "important_segments": [
    {
      "start": 10.0,
      "end": 35.0,
      "reason": "핵심 설명 구간"
    }
  ]
}
```

`important_segments`는 이후 프레임 샘플링 범위를 제한하는 데 사용됩니다. 각 항목은 최소한 `start`, `end` 값을 가져야 합니다.

## OCR 결과

경로: `runs/ocr/ocr_result.json`

```json
[
  {
    "frame_id": 0,
    "timestamp": 12.5,
    "image_path": "C:\\capstone\\Capstone_video-summarization\\runs\\frames\\frame_000001.jpg",
    "ocr_text": "화면에서 인식된 텍스트",
    "detected_language": "ko",
    "scene_type": "presentation_slide",
    "image_caption": "텍스트 정보가 포함된 화면입니다.",
    "importance_score": 0.8
  }
]
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `ocr_text` | string | EasyOCR가 추출한 텍스트 |
| `detected_language` | string | `ko`, `en`, `mixed`, `unknown` |
| `scene_type` | string | OCR 텍스트 기반 화면 유형. `generic_scene`(텍스트 없음), `chart_or_table`(표/그래프/성능 관련 키워드), `presentation_slide`(목차/개요/결론 등 발표 자료 키워드), `text_screen`(그 외 텍스트가 있는 화면) 중 하나 (`modules/ocr/image_caption.py`의 `classify_scene_type`) |
| `image_caption` | string | OCR 텍스트 기반 간단 캡션 |
| `importance_score` | number | 0.0에서 1.0 사이의 휴리스틱 중요도 |

앱의 요약 화면(`app/summary_timeline.py`)은 이 중 `scene_type`이 `chart_or_table`인 프레임을 우선으로 찾아 "표/차트 기반 주요 정보" 구간의 스크린샷으로 사용합니다.

## VLM 요약 결과

경로:

```text
runs/vlm/vlm_summary.txt
runs/vlm/vlm_summary_result.json
```

```json
{
  "source": {
    "ocr_json_path": "runs/ocr/ocr_result.json",
    "frame_count": 3
  },
  "results": [
    {
      "frame_id": 0,
      "timestamp": 12.5,
      "vlm_summary": "프레임 화면 요약"
    }
  ]
}
```

VLM 서버 응답 필드는 서버 구현에 따라 추가될 수 있습니다. 클라이언트는 각 결과 항목이 객체인지 검증합니다.

## 최종 요약 결과

경로:

```text
runs/final/final_summary.txt
runs/final/final_summary_result.json
```

**중요: 아래는 실제로 GPU 서버가 반환하는 형태입니다.** 최상위 키는 `source`, `final_summary`, `summary` 세 개뿐이며, `title`/`topics`/`main_topic`/`conclusion`/`keywords` 같은 구조화된 필드는 **실제 응답에는 존재하지 않습니다**. 핵심 주제, 주제별 요약, 표/차트 정보, 종합 결론이 모두 `summary`(그리고 동일한 내용의 `final_summary`) 안에 하나의 마크다운 텍스트로 들어있습니다. 타임라인도 별도 필드가 아니라 문단 안에 `(타임라인: 66.0 ~ 813.0)`처럼 자유 텍스트로 박혀 있습니다.

```json
{
  "source": {
    "stt_summary_json_path": "runs/llm/stt_summary_result.json",
    "vlm_summary_json_path": "runs/vlm/vlm_summary_result.json"
  },
  "final_summary": "# 제목\n\n## 핵심 주제\n- ...\n\n## 주요 내용\n\n### 1. 소제목 (타임라인: 0.0 ~ 3.5)\n- ...\n\n## 표/차트 기반 주요 정보\n\n### 1. 소제목 (타임라인: 1051.9 ~ 1066.9)\n- ...\n\n## 종합 결론\n- ...",
  "summary": "# 제목\n\n## 핵심 주제\n- ...\n\n## 주요 내용\n\n### 1. 소제목 (타임라인: 0.0 ~ 3.5)\n- ...\n\n## 표/차트 기반 주요 정보\n\n### 1. 소제목 (타임라인: 1051.9 ~ 1066.9)\n- ...\n\n## 종합 결론\n- ..."
}
```

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `source` | object | 최종 요약 생성에 사용된 STT/VLM 요약 JSON 파일 경로 2개 (`scripts/run_final_summary.py`가 추가) |
| `final_summary` | string | GPU 서버가 반환한 마크다운 텍스트 (`summary`와 동일한 내용) |
| `summary` | string | 위와 동일한 마크다운 텍스트. `runs/final/final_summary.txt`에 그대로 저장됨 |

`summary` 마크다운은 보통 다음 순서의 `##` 섹션으로 구성됩니다(GPU 서버 프롬프트에 따라 달라질 수 있어 고정된 스키마는 아닙니다).

```text
# (영상 제목)
## 핵심 주제
## 주요 내용
### N. 소제목 (타임라인: 시작 ~ 끝)
## 표/차트 기반 주요 정보
### N. 소제목 (타임라인: 시작 ~ 끝)
## 종합 결론
```

앱(`app/summary_result.py`, `app/summary_timeline.py`)은 이 마크다운을 파싱해서 화면에 표시합니다.

- `app/summary_result.py`의 `get_summary_markdown()`이 `summary`/`final_summary` 중 있는 값을 마크다운 텍스트로 꺼냅니다.
- `has_structured_summary()`는 `title`/`main_topic`/`topics`/`conclusion`/`keywords` 키가 있을 때만 참을 반환합니다. 이 키들은 **의도된/향후 지원용 구조화 스키마**일 뿐이며, 실제 GPU 서버 응답에서는 나타나지 않으므로 이 분기(`app/final_summary_view.py`의 `render_summary_data`에서 카드형 UI로 렌더링하는 경로)는 현재 사실상 사용되지 않습니다.
- 실제로는 항상 마크다운 텍스트 경로를 타며, `app/summary_timeline.py`의 `render_summary_with_timeline()`이 `### N. 제목 (타임라인: 시작 ~ 끝)` 패턴을 찾아 구간별 카드로 렌더링하고, `(타임라인: ...)` 표기를 `분:초` 형식의 클릭 가능한 뱃지로 바꿔 보여줍니다. 클릭하면 `<video>` 엘리먼트의 `currentTime`을 이동시켜 해당 지점부터 재생합니다.
- 제목에 "표"/"차트"가 포함된 섹션은 `runs/ocr/ocr_result.json`에서 해당 타임라인과 겹치고 `scene_type`이 `chart_or_table`인 프레임을 찾아 스크린샷도 함께 보여줍니다.

최종 JSON은 GPU 서버 응답을 그대로 보존하므로 위 세 키 외에 서버 구현 변경에 따라 추가 필드가 포함될 수 있습니다.
