# Services

API 계층과 모델 로더 사이에서 입력 정규화, 프롬프트 구성, 결과 파싱과 다중 단계 추론을 담당합니다.

`scripts/`는 HTTP와 작업 상태를 처리하고, `models/`는 실제 모델 실행만 담당합니다. 서비스 계층은 두 계층이 서로의 세부 구현에 직접 의존하지 않도록 연결합니다.

## 파일 구성

| 파일 | 역할 |
| --- | --- |
| `summary_service.py` | LLM/VLM 서비스 조립과 상위 호출 인터페이스 제공 |
| `llm_service.py` | STT 요약, 중요 구간 추출, 결과 파싱 |
| `vlm_service.py` | OCR 정규화, 이미지 매칭, 프레임별 시각 요약 |
| `final_service.py` | STT 요약과 VLM 요약을 종합한 강의 노트 JSON·마크다운 최종 요약 생성 |

## SummaryService

`SummaryService`는 서버가 사용하는 단일 진입점입니다.

```text
SummaryService
  +-- LLMService ----+
  |                  +-- shared generation Lock
  `-- VLMService ----+
```

LLM과 VLM에 같은 `Lock`을 전달하여 두 모델이 동시에 GPU 추론이나 해제를 수행하지 않게 합니다.

생성자는 `llm_loader`/`vlm_loader`를 선택적으로 받습니다. 생략하면 `LLMService`/`VLMService`가 각자 기본 로더(`LLM_BACKEND`에 따른 로컬 Qwen 또는 Claude API, 로컬 Qwen VLM)를 만들지만, `app/local_model_manager.py`는 신규 로컬 모델로 전환할 때 이 인자로 `MultimodalLoader`/`MiniCPMLoader` 인스턴스 하나를 LLM과 VLM 양쪽에 동일하게 주입해 하나의 체크포인트를 공유시킵니다.

주요 메서드:

| 메서드 | 설명 |
| --- | --- |
| `summarize_stt()` | STT 전체 요약 |
| `get_important_segments_in_chunks()` | 긴 STT 구간을 나누어 중요 구간 추출 |
| `summarize_frame()` | 단일 프레임 분석 |
| `summarize_frames()` | OCR 결과와 여러 프레임 분석 |
| `summarize_final_note()` | STT/VLM 요약 자료를 통합한 강의 노트 JSON과 마크다운 최종 요약 |
| `summarize_final()` | `summarize_final_note()`의 마크다운만 반환하는 호환용 래퍼 |
| `unload_llm()` | LLM GPU 메모리 해제 |
| `unload_vlm()` | VLM GPU 메모리 해제 |

## LLMService

### STT 요약

`summarize_stt()`는 STT 원문을 강의 녹취로 보고, 학습자가 복습할 수 있는 강의 요약을 요구하는 한국어 프롬프트를 구성합니다.

- 다룬 개념을 강의 순서대로 정리
- 새 용어는 `'작은따옴표'`로 표시하고 강사가 설명한 정의를 함께 기록
- 예시·비유·예제 풀이는 핵심만 유지
- "중요하다", "시험에 나온다" 등 강사가 강조한 내용은 반드시 포함
- 출석 확인, 잡담, 장비 점검, 반복 설명 제거
- 전문 용어 STT 오류는 문맥상 명확할 때만 보정, 원문에 없는 설명·예시·수치 생성 금지
- 전체 1200자 이내, 강의가 길면 예시를 줄이더라도 다룬 주제는 끝까지 유지

출력 형식은 `## 강의 요약` 아래 `### 학습 주제`, `### 핵심 개념`(`- '용어': 설명`), `### 강의 흐름`, `### 강조 사항 및 공지`(과제·시험·다음 수업 공지가 없으면 "없음") 순서입니다.

### 긴 강의: 구간별 요약 후 통합

프롬프트가 로더의 입력 토큰 상한(`loader.max_input_tokens`, `loader.count_prompt_tokens()`로 실제 토큰 수 확인) 안에 들면 위 프롬프트로 한 번에 요약합니다. 넘으면 앞부분을 자르지 않고 STT 세그먼트 기준으로 나눠 요약한 뒤 통합합니다(map-reduce).

1. 구간 나누기: 중요 구간 추출과 같은 `split_segments()`로 세그먼트를 자르지 않고 묶습니다. 묶음 크기는 상한과 실제 토큰/글자 비율로 정하고, 실제 프롬프트가 상한을 넘는 묶음만 반으로 더 나눕니다(세그먼트 하나가 넘으면 공백 경계로 분할).
2. 구간 요약: 각 구간을 `[분:초] 내용` 줄로 넣고, 경계 문맥으로 이전 구간 요약 끝 600자와 이전 구간 STT 끝 300자를 "참고용, 다시 정리하지 말 것"으로 함께 넣습니다. 구간당 생성 토큰은 512입니다.
3. 통합: 구간 요약들을 `#### 구간 n (시작~끝)`으로 이어 기존과 같은 `## 강의 요약` 형식으로 통합합니다. 반복된 개념은 처음 나온 시각 기준으로 한 번만 적고, 강의 흐름 항목에 `[분:초]`를 붙입니다. 구간이 많아 통합 프롬프트가 상한을 넘으면 인접 구간끼리 먼저 합친 뒤 다시 통합합니다.

세그먼트 없이 `full_text`만 온 요청은 공백 경계로 나눈 시간 없는 세그먼트(`[--:--]`)로 처리합니다. 입력 상한이 없는 백엔드(Claude API)는 항상 한 번에 요약합니다. 구간 요약 중에는 작업 상태에 `긴 강의를 구간별로 요약하고 있습니다. (i/n)`이 표시됩니다.

`max_new_tokens`는 호출부에서 직접 정하지 않고 `configs/inference_config.py`의 `SUMMARY_LEVEL_PRESETS`(`summary_level`별 프리셋)에서 가져옵니다. 직접 호출할 때의 기본값은 `LECTURE_STT_MAX_NEW_TOKENS`(`LLM_INFERENCE_CONFIG.max_new_tokens_limit`, `1024`)입니다. 개념·정의·강조 사항까지 담으면 512토큰으로는 뒷부분 주제가 잘리기 때문입니다. `LLMService`는 `_validate_max_new_tokens()`로 이 값이 `1` 이상 `LLM_INFERENCE_CONFIG.max_new_tokens_limit`(`1024`) 이하인지만 검증합니다.

### 요약 레벨(summary_level) 프리셋

`app/inference_jobs.py`는 요청의 `summary_level`(`simple`/`standard`/`detailed`)로 `SUMMARY_LEVEL_PRESETS`에서 `SummaryLevelPreset`을 조회해 각 단계에 다음 값을 전달합니다.

| 값 | STT 요약 토큰 | 중요 구간 추출 | 구간 청크 크기 | VLM 토큰 | 최종 요약 토큰 |
| --- | --- | --- | --- | --- | --- |
| `simple` | 256 | 생략 | 20000자 | 96 | 1024 |
| `standard`(기본값) | 1024 | 실행 | 12000자 | 160 | 3072 |
| `detailed` | 1024 | 실행 | 8000자 | 384 | 4096 |

`simple`은 프레임/OCR/VLM 단계를 쓰지 않는 클라이언트를 위한 프리셋이라 `extract_important_segments=False`로 두어 여러 번의 청크별 LLM 호출(중요 구간 추출)을 아예 생략합니다. `standard`의 최종 요약 토큰이 `3072`인 이유는 최종 요약을 강의 노트 JSON으로 출력해 마크다운보다 토큰이 더 들고, 출력이 잘리면 JSON을 읽을 수 없기 때문입니다.

### 최종 요약

`final_service.py`는 STT 요약 텍스트/JSON과 VLM 요약 텍스트/JSON을 하나의 프롬프트로 통합해 강의 노트를 생성합니다. `stt_text`/`vlm_text`(txt)는 선택 입력이며, STT 텍스트가 없으면 `stt_json`의 `summary` 필드를 대신 사용합니다. STT 중요 구간은 `- [시작초 ~ 끝초] topic: reason` 형식(최대 `MAX_IMPORTANT_SEGMENTS`=8개)으로 전달합니다.

VLM JSON은 `_format_vlm_json()`이 다음 순서로 줄여 `[VLM 화면별 요약]`으로 전달합니다.

1. 각 결과의 `vlm_fields`(없는 이전 결과는 `vlm_summary`를 `parse_vlm_fields()`로 파싱)를 읽어 `has_content`가 거짓인 프레임(강사 화면, 내용 없음)을 제외
2. 시간순으로 정렬한 뒤 연속된 프레임의 제목이 같으면 한 항목(`시작 ~ 끝` 구간)으로 병합
3. 항목이 `MAX_VLM_ITEMS`(`16`)개를 넘으면 전체를 같은 크기 구간으로 나눠 구간마다 우선순위(`SCREEN_PRIORITY`: 수식·코드·표·그래프·도식 > 슬라이드·판서 > 기타)와 내용 길이가 가장 큰 항목을 선택
4. 항목은 `- [시작 ~ 끝] 화면 유형 | 제목`, `내용:`, `수식·코드·수치:` 줄로 만들고 항목당 `300`자, 전체 `5000`자로 제한

필터링 결과 화면 자료가 비면(강사 화면만 있는 강의 등) 오류 대신 `NO_VLM_CONTENT` 안내 문구를 넣습니다. VLM 입력(`vlm_text`/`vlm_json`)이 아예 없거나 STT 섹션이 비어 있으면 `ValueError`입니다.

`summarize_final_note()`의 처리 순서:

```text
NOTE_PROMPT로 강의 노트 JSON 생성
  -> extract_json_object() + normalize_lecture_note()
  -> 실패하면 오류 내용을 NOTE_RETRY_SUFFIX로 덧붙여 한 번 더 생성
     (생성이 결정적이라 같은 프롬프트는 같은 답을 내므로 입력을 바꿈)
  -> 그래도 실패하면 MARKDOWN_FALLBACK_PROMPT로 마크다운 직접 생성
```

`NOTE_PROMPT`가 요구하는 JSON 구조:

```json
{
  "title": "강의 제목",
  "key_points": ["핵심 내용 1~3개"],
  "terms": [{"term": "용어", "definition": "정의"}],
  "chapters": [
    {"title": "챕터 제목", "start": 125.7, "end": 310.0, "points": ["..."], "screen_notes": ["..."]}
  ],
  "visuals": [
    {"type": "표 | 그래프 | 수식 | 코드 | 도식", "title": "...", "start": 200.0, "end": null, "content": ["..."], "meaning": "..."}
  ],
  "conclusion": ["복습할 내용 2~4개"],
  "notices": ["과제·시험·다음 수업 공지"]
}
```

챕터는 3~7개로 나누고, `start`/`end`는 입력 자료의 초 단위 숫자를 그대로 쓰며 HH:MM:SS로 바꾸지 않습니다(모르면 `null`).

- `extract_json_object()`: `<think>` 블록과 코드 블록 표시를 지우고 첫 `{`부터 마지막 `}`까지를 읽습니다. 끝 쉼표는 제거해 한 번 더 시도하며, 닫히지 않은 객체(길이 제한으로 잘림)는 `ValueError`입니다.
- `normalize_lecture_note()`: 입력 자료의 시간(`collect_known_times()`) 최댓값보다 `TIME_TOLERANCE_SEC`(`5`초) 넘게 큰 시간, 음수·숫자가 아닌 시간은 `null`로 바꾸고 `end < start`면 `end`를 `null`로 바꿉니다. `<...>` 자리표시를 그대로 베낀 값과 빈 항목은 버리고, `NOTE_LIMITS`(key_points 3, terms 15, chapters 10, points 6, screen_notes 4, visuals 10, content 6, conclusion 5, notices 5) 개수를 넘으면 자릅니다. `visuals[].type`은 `VISUAL_TYPES` 중 하나로 정규화(그 외는 `기타`)합니다. 고친 내용은 `warnings`로 반환하며, 남은 챕터가 없으면 `ValueError`입니다.
- `render_note_markdown()`: 강의 노트를 앱의 기존 마크다운 파서가 읽는 형식으로 바꿉니다. `# 제목` 아래 `## 핵심 주제`, `## 주요 용어`, `## 주요 내용`(`### N. 챕터 (타임라인: 시작초 ~ 끝초)`, 화면 내용은 `- VLM 요약 자료에서는 ...`), `## 표/차트 기반 주요 정보`, `## 종합 결론`, `## 공지 사항` 순서이며 빈 섹션은 생략합니다. 시간을 모르면 `(타임라인: 확인 필요)`입니다.

반환값:

| 키 | 설명 |
| --- | --- |
| `lecture_note` | 정규화된 강의 노트 dict. 마크다운 대체 시 `None` |
| `markdown` | `render_note_markdown()` 결과 또는 대체 프롬프트의 마크다운 |
| `format` | `json` 또는 `markdown_fallback` |
| `attempts` | JSON 시도별 `{raw, error}` 목록 |
| `warnings` | `normalize_lecture_note()`가 고친 내용 |

`max_new_tokens`는 위 표의 "최종 요약 토큰" 값을 사용하며(직접 호출 기본값 `DEFAULT_FINAL_MAX_NEW_TOKENS`=`3072`), `FinalService._validate_max_new_tokens()`는 이 값이 `1` 이상 `MAX_FINAL_NEW_TOKENS_LIMIT`(`4096`) 이하인지 검증합니다.

### 중요 구간 추출

각 세그먼트는 토큰 사용량을 줄이기 위해 다음 행 형식으로 모델에 전달됩니다.

```text
segment_id|start|end|text
```

모델 출력 형식:

```text
segment_id|start|end|topic|reason
```

파서는 정수 `segment_id`, 실수 `start`, `end`를 검증하고 객체 배열로 변환합니다. 형식이 잘못된 행은 건너뛰며, 한 묶음에서 유효한 결과가 하나도 없으면 `ValueError`를 발생시킵니다.

프롬프트는 강의 화면(슬라이드, 판서, 코드, 도표)을 함께 분석해야 할 구간을 고르도록 다음 기준을 줍니다: 새 개념·용어가 처음 정의되는 구간, "여기 보시면", "이 식은"처럼 화면을 가리키는 말이 나오는 구간, 수식 유도·코드 설명·예제 풀이 구간, 강사가 강조하거나 정리하는 구간. 출석·잡담·장비 점검·단순 반복은 제외합니다.

파싱 후 `_align_to_input()`이 모델이 쓴 시간을 입력 묶음 기준으로 바로잡습니다. `start`/`end`가 모두 입력 구간의 경계값이고 대표 `segment_id` 구간을 포함하면 그대로 두고, 아니면(예: `segment_id`를 시간으로 착각) 해당 `segment_id` 구간의 실제 시간으로 바꿉니다. 묶음에 없는 `segment_id`는 버립니다.

### 세그먼트 분할

`split_segments()`는 세그먼트 내부를 자르지 않고 JSON 직렬화 길이를 기준으로 묶습니다. 기본 묶음 크기는 `12000`자입니다.

```text
전체 segments
  -> 문자 길이 기준 chunk 생성
  -> chunk별 LLM 호출
  -> 출력 파싱
  -> 결과 배열 병합
```

## VLMService

### 지원 이미지 입력

`VLMService`는 다음 입력을 PIL RGB 이미지로 정규화합니다.

- 문자열 파일 경로
- `Path`
- `bytes`, `bytearray`
- binary file object
- PIL `Image`

분석이 끝나면 서비스가 생성한 PIL 이미지를 `finally`에서 닫습니다.

### OCR 입력

`load_ocr_results()`가 지원하는 형식:

- JSON 파일 경로
- JSON 문자열
- 객체 배열
- `frames`, `results`, `ocr_results` 키로 감싼 객체

각 항목에 `frame_id`가 없으면 배열 인덱스를 사용합니다. 중복 `frame_id`는 허용하지 않습니다.

권장 OCR 항목:

```json
{
  "frame_id": 0,
  "timestamp": 12.5,
  "image_path": "frame_000001.jpg",
  "ocr_text": "화면에서 인식된 텍스트",
  "detected_language": "ko",
  "scene_type": "slide"
}
```

### 프레임 매칭

`summarize_frames()`의 `frames`가 sequence이면 OCR 항목과 이미지의 순서 및 개수가 같아야 합니다.

mapping이면 다음 키를 순서대로 확인합니다.

1. `frame_id`
2. 문자열로 변환한 `frame_id`
3. OCR의 전체 `image_path`
4. `image_path`의 파일명

매칭되지 않은 프레임이 있으면 추론을 시작하지 않고 오류를 반환합니다.

### 프레임 프롬프트

`summarize_frame()`은 강의 영상 프레임과 OCR 결과를 주고, 다음 4줄만 출력하도록 요구합니다. 화면과 OCR에서 확인되는 내용만 쓰고, 읽을 수 없는 글자·수치는 "판독 불가", 해당 내용이 없으면 "없음"으로 적게 합니다.

```text
화면 유형: <슬라이드, 판서, 코드, 표, 그래프, 수식, 도식, 강사 화면, 기타 중 하나>
제목: <화면에 보이는 제목>
핵심 내용: <화면이 설명하는 내용, 한두 문장>
수식·코드·수치: <화면의 식, 코드, 수치를 그대로>
```

`parse_vlm_fields()`는 이 `항목 이름: 값` 줄 출력을 필드로 나눕니다. 항목 이름의 공백·구분자 차이(`유형`, `내용`, `수식/코드` 등)를 허용하고, 항목 이름이 없는 줄은 앞 항목에 이어 붙입니다(여러 줄 코드·수식). "없음" 같은 값은 빈 문자열로 바꾸고, `normalize_screen_type()`이 화면 유형을 `SCREEN_TYPES` 중 하나로 정규화합니다. `has_content`는 강사 화면이 아니면서 핵심 내용이나 수식·코드·수치가 있을 때만 참입니다. 항목을 하나도 찾지 못하면 `parsed=False`, `screen_type=None`이고 원문 전체를 `content`에 둡니다.

### VLM 결과

원래 OCR 항목을 유지하고 `vlm_summary`(모델 원문)와 `vlm_fields`(파싱 결과)를 추가합니다.

```json
{
  "frame_id": 0,
  "timestamp": 12.5,
  "ocr_text": "...",
  "vlm_summary": "화면 유형: 슬라이드\n제목: 경사하강법\n핵심 내용: ...\n수식·코드·수치: ...",
  "vlm_fields": {
    "screen_type": "슬라이드",
    "title": "경사하강법",
    "content": "...",
    "formula": "...",
    "has_content": true,
    "parsed": true
  }
}
```

진행 콜백을 전달하면 프레임마다 다음 형태로 호출합니다.

```python
progress_callback("vlm_frames", current_index, total_frames)
```

## 동시성과 모델 해제

모든 모델 생성과 `unload()`는 공유 lock 내부에서 실행됩니다. 서비스 메서드에서 별도 스레드를 만들지 않으며, 비동기 작업 관리는 `app/inference_jobs.py`가 담당합니다.

```text
작업 실행기
  -> 서비스 메서드 호출
  -> shared lock 획득
  -> loader 추론
  -> shared lock 해제
  -> 작업 종료 시 unload
```

## 기능 확장 원칙

- 프롬프트와 출력 형식 변경: 해당 서비스에서 수정
- 모델 클래스나 전처리 변경: `models/`에서 수정
- HTTP 필드와 상태 응답 변경: `scripts/`에서 수정
- 새 모델이 기존 GPU를 공유한다면 `SummaryService`의 공용 lock 사용
- 긴 입력은 한 번에 모델에 전달하기보다 기존 chunk 패턴 사용
- 모델 출력은 가능한 한 명시적인 형식으로 제한하고 파서를 함께 작성
