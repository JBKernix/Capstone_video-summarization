# Frame Sampling

## 개요

`modules/preprocess/frame_sampler.py`는 STT 요약 결과의 중요 구간 안에서 일정 간격으로 프레임을 추출하고, 각 프레임의 timestamp와 이미지 경로를 `frame_metadata.json`에 저장한다.

전체 파이프라인에서는 다음 순서로 실행된다.

```text
STT 결과
  -> LLM 요약 및 important_segments 생성
  -> 중요 구간 interval 또는 화면 전환 프레임 추출
  -> 프레임 OCR 분석
```

샘플링 방식은 `interval`과 `scene_change` 중에서 선택한다. 두 방식 모두 전체 파이프라인에서는 STT 요약의 중요 구간 내부에만 적용된다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/frame_sampler.py` | 중요 구간 로드, interval/화면 전환 프레임 추출, metadata 생성 |
| `modules/preprocess/video_info.py` | 영상 길이, 해상도, FPS 조회 |
| `modules/preprocess/ffmpeg_utils.py` | FFmpeg 실행과 기존 이미지 삭제 |
| `scripts/run_preprocess.py` | 프레임 추출 단독 실행 |
| `scripts/run_pipeline.py` | STT 요약 이후 중요 구간 프레임 추출 호출 |

## 기본 설정

```python
DEFAULT_SAMPLING_METHOD = "interval"
DEFAULT_INTERVAL_SECONDS = 10.0
DEFAULT_SCENE_THRESHOLD = 0.7
DEFAULT_SCENE_MIN_GAP_SECONDS = 1.0
```

기본 방식은 interval이며 각 중요 구간의 시작 시점부터 기본 10초 간격으로 프레임을 추출한다. 화면 전환 방식은 FFmpeg scene score가 임계값을 넘는 프레임을 선택한다.

## 출력 구조

```text
runs/
  frames/
    frame_000001.jpg
    frame_000002.jpg
  metadata/
    frame_metadata.json
```

metadata 예시:

```json
[
  {
    "frame_id": 0,
    "timestamp": 120.0,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "interval"
  }
]
```

`image_path`는 가능하면 `project_root` 기준 상대 경로로 저장한다. 파일이 프로젝트 루트 밖에 있으면 절대 경로를 사용한다.

## 실행 흐름

```text
sample_frames()
  -> important_segments_path가 있으면 중요 구간 로드
  -> method 확인
      -> interval: sample_interval_frames()
      -> scene_change: sample_scene_change_frames()
  -> 기존 frame_*.jpg 삭제
  -> metadata/frame_metadata.json 저장
```

`important_segments_path`를 전달하지 않으면 선택한 방식으로 전체 영상을 추출한다. 전체 파이프라인에서는 LLM 요약 JSON 경로를 항상 전달한다.

## 중요 구간 입력

LLM STT 요약 결과는 `important_segments` 배열을 포함해야 한다.

```json
{
  "important_segments": [
    {"start": 10.0, "end": 30.0},
    {"start": 90.0, "end": 180.0}
  ]
}
```

`important_segments`가 JSON 문자열로 저장된 경우에도 다시 파싱한다. 각 항목에서 `start`와 `end`가 모두 있는 구간만 사용한다.

시간 구간 정규화 규칙:

1. 음수 시작 시점은 `0.0`으로 보정한다.
2. 종료 시점이 시작 시점 이하인 구간은 제외한다.
3. 시작 시점 기준으로 정렬한다.
4. 겹치거나 경계가 맞닿은 구간은 하나로 합친다.

중요 구간 목록이 비어 있거나 유효한 구간이 없으면 전체 영상을 대신 추출하지 않는다. 빈 `frame_metadata.json`을 생성하고 추출 프레임 수는 0이 된다.

## timestamp 생성

### interval

각 구간의 시작점부터 종료점까지 interval을 더해 추출 시점을 만든다.

```python
timestamp = start
while timestamp <= end:
    timestamps.append(timestamp)
    timestamp += interval_seconds
```

예를 들어 `(90, 180)` 구간에 interval이 60초이면 `90`, `150`초 프레임을 추출한다. 종료 시점과 정확히 일치하는 timestamp도 포함하며, 겹친 구간에서 중복된 timestamp는 한 번만 사용한다.

각 프레임은 FFmpeg의 `-ss`와 `-frames:v 1`을 이용해 개별 추출한다.

### scene_change

다음 조건을 조합한 FFmpeg `select` 필터를 사용한다.

```text
scene score > scene_threshold
AND 이전 선택 프레임과 scene_min_gap_seconds 이상 차이
AND important_segments 시간 범위 내부
```

선택된 timestamp는 `showinfo` 로그의 `pts_time`에서 읽는다. 이미지 수와 timestamp 수가 다르면 잘못된 metadata 생성을 막기 위해 `RuntimeError`를 발생시킨다.

## 주요 함수

| 함수 | 역할 |
| --- | --- |
| `sample_frames()` | 선택한 샘플링 방식 호출 |
| `sample_interval_frames()` | 전체 영상 또는 지정 구간에서 interval 프레임 추출 |
| `sample_scene_change_frames()` | 전체 영상 또는 지정 구간에서 화면 전환 프레임 추출 |
| `load_important_time_ranges()` | LLM 요약 JSON에서 중요 구간 로드 |
| `_normalize_time_ranges()` | 시간 구간 보정, 정렬, 병합 |
| `_build_interval_timestamps()` | 중요 구간별 추출 timestamp 생성 |
| `_write_metadata()` | `FrameMetadata` 목록을 UTF-8 JSON으로 저장 |
| `load_frame_metadata()` | metadata JSON을 `utf-8-sig`로 로드 |

## CLI 사용

전체 파이프라인:

```powershell
python scripts/run_pipeline.py --method interval --interval-seconds 10

python scripts/run_pipeline.py `
  --method scene_change `
  --scene-threshold 0.7 `
  --scene-min-gap-seconds 1.0
```

전처리 단독 실행:

```powershell
python scripts/run_preprocess.py `
  --method scene_change `
  --important-segments-json runs/llm/stt_summary_result.json
```

## 예외와 주의 사항

| 상황 | 결과 |
| --- | --- |
| `interval_seconds <= 0` | `ValueError` |
| scene threshold가 0과 1 사이가 아님 | `ValueError` |
| scene 최소 간격이 음수 | `ValueError` |
| 입력 영상이 없음 | `FileNotFoundError` |
| 중요 구간 JSON 파일이 없음 | `FileNotFoundError` |
| 중요 구간 JSON 형식이 잘못됨 | JSON 또는 형 변환 예외 전파 |

같은 `run_dir`을 재사용하면 기존 `frame_*.jpg`와 metadata를 덮어쓴다.
