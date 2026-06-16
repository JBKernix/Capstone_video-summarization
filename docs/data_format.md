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
| `scene_type` | string | OCR 텍스트 기반 화면 유형 |
| `image_caption` | string | OCR 텍스트 기반 간단 캡션 |
| `importance_score` | number | 0.0에서 1.0 사이의 휴리스틱 중요도 |

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

```json
{
  "source": {
    "stt_summary_path": "runs/llm/stt_summary.txt",
    "stt_summary_json_path": "runs/llm/stt_summary_result.json",
    "vlm_summary_path": "runs/vlm/vlm_summary.txt",
    "vlm_summary_json_path": "runs/vlm/vlm_summary_result.json"
  },
  "summary": "음성 요약과 화면 요약을 통합한 최종 요약"
}
```

최종 JSON은 GPU 서버 응답을 보존하므로 `summary` 외 추가 필드가 포함될 수 있습니다.
