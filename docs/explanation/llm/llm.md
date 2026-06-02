# LLM Pipeline

이 문서는 `modules/llm` 모듈의 현재 상태와 예정된 역할을 설명한다. 현재 `prompt_builder.py`와 `summarizer.py` 파일은 생성되어 있지만 실제 구현은 아직 비어 있다. 따라서 이 문서는 기존 전처리, vision, STT 결과를 바탕으로 LLM 요약 단계가 어떤 입력을 받아 어떤 출력을 만들어야 하는지 정리한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/llm/prompt_builder.py` | 현재 구현 없음. STT/vision 결과를 요약 프롬프트로 구성할 예정 |
| `modules/llm/summarizer.py` | 현재 구현 없음. LLM 호출 또는 로컬 요약 실행을 담당할 예정 |
| `scripts/run_summary.py` | 요약 실행 진입점으로 사용할 예정 |
| `configs/llm_config.yaml` | LLM 모델과 요약 옵션 설정 위치 |
| `runs/stt/stt_result.json` | 요약 입력으로 사용할 음성 인식 결과 |
| `runs/vision/vision_result.json` | 요약 입력으로 사용할 시각 정보 결과 |

## 예정 실행 흐름

```text
scripts/run_summary.py
    -> stt_result.json 로드
    -> vision_result.json 로드
    -> build_summary_prompt()
        -> STT full_text 정리
        -> 중요 프레임 정보 정리
        -> 타임라인 기반 근거 구성
    -> summarize()
        -> LLM 또는 요약 모델 호출
    -> summary_result.json 저장
    -> summary_result.txt 저장
```

현재는 이 흐름이 구현되어 있지 않다.

## 1. `prompt_builder.py`

`prompt_builder.py`는 후속 구현에서 요약 프롬프트를 만드는 역할을 맡을 수 있다.

예상 입력은 다음과 같다.

| 입력 | 의미 |
| --- | --- |
| STT 결과 | 영상의 음성 내용을 segment 단위로 정리한 데이터 |
| vision 결과 | 프레임별 OCR, 장면 유형, 중요도 점수 |
| 요약 옵션 | 요약 길이, 언어, 출력 형식 등 |

STT 결과에서 사용할 수 있는 주요 필드는 다음과 같다.

```json
{
  "language": "ko",
  "segment_count": 2,
  "segments": [
    {
      "segment_id": 0,
      "start": 0.0,
      "end": 3.2,
      "text": "영상에서 말한 내용"
    }
  ],
  "full_text": "영상 전체 음성 텍스트"
}
```

vision 결과에서 사용할 수 있는 주요 필드는 다음과 같다.

```json
{
  "frame_id": 0,
  "timestamp": 10.0,
  "ocr_text": "슬라이드 텍스트",
  "scene_type": "presentation_slide",
  "image_caption": "비교적 많은 텍스트 정보가 포함된 장면입니다.",
  "importance_score": 0.8
}
```

프롬프트 구성 시 고려할 수 있는 기준은 다음과 같다.

1. STT의 `full_text`를 요약의 기본 내용으로 사용한다.
2. `importance_score`가 높은 프레임의 OCR 텍스트를 보조 근거로 사용한다.
3. STT segment 시간과 vision frame timestamp를 함께 사용해 시간순 흐름을 만든다.
4. OCR 텍스트가 STT에 없는 키워드를 보완할 수 있도록 프롬프트에 포함한다.

## 2. `summarizer.py`

`summarizer.py`는 후속 구현에서 실제 요약을 수행하는 역할을 맡을 수 있다.

예상 역할은 다음과 같다.

| 역할 | 설명 |
| --- | --- |
| 모델 설정 로드 | `configs/llm_config.yaml`에서 모델명, 온도, 길이 제한 등을 읽음 |
| 프롬프트 실행 | `prompt_builder.py`가 만든 프롬프트를 LLM에 전달 |
| 결과 정규화 | 제목, 핵심 요약, 타임라인, 키워드 등을 구조화 |
| 결과 저장 | JSON/TXT 또는 Markdown으로 저장 |

예상 출력 구조는 다음과 같다.

```json
{
  "title": "영상 요약 제목",
  "summary": "영상 전체 핵심 요약",
  "key_points": [
    "핵심 내용 1",
    "핵심 내용 2"
  ],
  "timeline": [
    {
      "start": 0.0,
      "end": 30.0,
      "summary": "초반부 내용"
    }
  ]
}
```

## 입력 파일 형식

LLM 요약 단계는 최소한 다음 두 결과 파일을 입력으로 사용할 수 있다.

```text
runs/stt/stt_result.json
runs/vision/vision_result.json
```

STT 결과는 음성 기반 내용의 중심 입력이고, vision 결과는 화면 텍스트와 장면 유형을 보완 입력으로 사용할 수 있다.

## 출력 파일 형식

후속 구현에서 사용할 수 있는 기본 출력 위치는 다음과 같다.

```text
runs/summary/summary_result.json
runs/summary/summary_result.txt
```

JSON은 애플리케이션 표시나 후처리에 사용하고, TXT 또는 Markdown은 사람이 바로 읽는 용도로 사용할 수 있다.

## 실패 처리

현재 구현이 없으므로 실제 실패 처리는 아직 정의되어 있지 않다. 후속 구현에서는 다음 상황을 명확히 처리해야 한다.

| 상황 | 처리 방향 |
| --- | --- |
| STT 결과 파일 없음 | `FileNotFoundError` 또는 사용자 친화적 오류 메시지 |
| vision 결과 파일 없음 | vision 없이 STT만으로 요약할지 여부 결정 |
| LLM API 오류 | 재시도 또는 명확한 실패 메시지 |
| 입력 텍스트가 너무 김 | chunk 요약 후 병합 |
| 요약 결과가 비어 있음 | 실패로 처리하고 빈 결과 저장 방지 |

## 현재 한계

1. `prompt_builder.py`와 `summarizer.py`는 아직 구현되어 있지 않다.
2. LLM 제공자, 모델명, API 키 처리 방식이 정해져 있지 않다.
3. 긴 영상의 입력 길이 제한 처리 전략이 아직 없다.
4. STT와 vision 정보를 어떤 비율로 반영할지 정해져 있지 않다.
5. 결과 JSON schema가 확정되어 있지 않다.

이 문서는 후속 LLM 요약 구현 시 입력/출력 계약과 모듈 역할을 정리하기 위한 기준 문서다.
