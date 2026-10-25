# 프레임 샘플링

`modules/preprocess/frame_sampler.py`는 영상에서 JPG 프레임을 추출하고 `frame_metadata.json`을 생성합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/frame_sampler.py` | representative/interval/scene_change 샘플링 구현 |
| `modules/preprocess/video_info.py` | 영상 정보 조회, 진행률 계산 기준 duration 제공 |
| `modules/preprocess/ffmpeg_utils.py` | `run_ffmpeg_with_progress()`/`run_ffmpeg()` 실행과 showinfo timestamp 파싱 |
| `modules/common/progress.py` | `report_progress()`로 `STEP_FRAME_EXTRACTION` 진행률 보고 |
| `modules/common/json_utils.py` | 메타데이터 JSON 읽기/쓰기(`load_json`/`save_json`) |
| `scripts/run_preprocess.py` | 프레임 샘플링 단독 실행 |
| `scripts/run_pipeline.py` | STT 요약 이후 주요 구간 샘플링 호출 |

## 기본값

```python
DEFAULT_SAMPLING_METHOD = "representative"
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_SCENE_THRESHOLD = 0.5
DEFAULT_SCENE_MIN_GAP_SECONDS = 1.0
DEFAULT_CANDIDATE_INTERVAL_SECONDS = 2.0   # representative 후보 추출 간격
DEFAULT_MAX_FRAMES_PER_SEGMENT = 4         # representative 구간당 최대 프레임 수
FULL_VIDEO_WINDOW_SECONDS = 60.0           # 구간 없이 영상 전체를 다룰 때 나누는 길이
```

지원하는 방식은 `representative`(기본), `interval`, `scene_change`입니다(`SAMPLING_METHOD_CHOICES`).

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
    "timestamp": 10.0,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "representative",
    "segment_id": 0
  }
]
```

`segment_id`는 representative 방식에서만 들어가며, 프레임이 속한 중요 구간 번호(정규화된 구간 순서 기준, 0부터)입니다. OCR 단계가 이 값을 `ocr_result.json`에 그대로 옮깁니다.

## 실행 흐름

```text
sample_frames()
  -> important_segments_path가 있으면 load_important_time_ranges()
  -> method 확인
      -> representative: sample_representative_frames()
      -> interval: sample_interval_frames()
      -> scene_change: sample_scene_change_frames()
  -> runs/frames/frame_*.jpg 생성
  -> runs/metadata/frame_metadata.json 저장
```

## representative 방식 (기본)

중요 구간마다 **화면이 바뀐 만큼만** 대표 프레임을 추출합니다. 화면이 그대로인 구간은 1장, 슬라이드가 여러 번 바뀐 구간은 여러 장이 됩니다.

```bash
python scripts/run_pipeline.py --video data/input/sample.mp4 --method representative --max-frames-per-segment 4
```

1. 구간마다 `_segment_candidates()`가 ffmpeg 한 번으로 후보를 뽑습니다. `-ss <시작> -t <길이>`를 입력 옵션으로 두고 `fps=1/2,mpdecimate,showinfo` 필터를 써서, 2초 간격 후보 중 직전에 남긴 후보와 거의 같은 화면은 버립니다(A→B→A처럼 돌아온 화면은 다시 남습니다). showinfo 시각은 구간 시작 기준이라 구간 시작 시각을 더합니다.
2. 후보가 `max_frames_per_segment`(기본 4)장을 넘으면 `_select_evenly()`가 처음과 끝을 포함해 시간상 고르게 줄입니다.
3. 후보가 하나도 없으면(구간이 영상 끝을 넘는 등) `_extract_single_frame()`으로 구간 가운데 시점 한 장을 씁니다. 그것도 실패하면 구간을 건너뜁니다.
4. 남긴 후보는 `frame_000001.jpg`처럼 전체 순번으로 이름을 바꾸고, 나머지 후보 파일(`_candidate_*.jpg`)은 지웁니다.

- **시간 구간 미지정**: 영상 전체를 `FULL_VIDEO_WINDOW_SECONDS`(60초) 길이로 나눈 구간마다 같은 방식으로 처리합니다. 영상 길이를 알 수 없으면 interval 방식으로 대신합니다.
- **시간 구간 지정**: LLM이 준 구간이 영상 길이를 넘으면 FFmpeg가 빈 출력으로 실패하므로, 정규화 전에 영상 길이 안으로 자릅니다.
- 진행률은 구간 하나를 마칠 때마다 `report_progress(STEP_FRAME_EXTRACTION, "대표 프레임 추출 중 (i/N 구간)", ...)`로 보고합니다. 구간마다 블로킹 방식 `run_ffmpeg()`를 씁니다.

## interval 방식

전체 영상 또는 지정된 시간 구간에서 일정 간격으로 프레임을 추출합니다.

```bash
python scripts/run_preprocess.py --method interval --interval-seconds 5
```

- **시간 구간 미지정**: `-vf fps=1/interval_seconds` 필터로 영상 전체를 한 번에 처리합니다. 이때는 `run_ffmpeg_with_progress()`를 사용해 ffmpeg 진행률을 실시간으로 받아 `report_progress(STEP_FRAME_EXTRACTION, ...)`로 보고합니다.
- **시간 구간 지정**: `_sample_interval_frames_in_ranges()`가 각 구간의 시작점부터 종료점까지 `interval_seconds` 간격으로 timestamp를 만들고(중복 timestamp는 제거), timestamp 하나마다 `-ss <timestamp> -frames:v 1`로 개별 ffmpeg 프로세스를 실행합니다. 이 경로는 블로킹 방식인 `run_ffmpeg()`를 그대로 사용하며, 프레임 하나를 추출할 때마다 다음과 같이 진행률을 보고합니다.

```python
report_progress(
    STEP_FRAME_EXTRACTION,
    f"프레임 추출 중 ({index + 1}/{total_timestamps})",
    (index + 1) / total_timestamps * 100,
)
```

## scene_change 방식

FFmpeg `select` 필터의 scene score를 사용해 장면 전환 프레임을 추출합니다.

```bash
python scripts/run_preprocess.py --method scene_change --scene-threshold 0.5 --scene-min-gap-seconds 1.0
```

조건은 다음과 같습니다.

```text
scene score > scene_threshold
AND 이전 선택 프레임과 scene_min_gap_seconds 이상 차이
AND important_segments가 있으면 해당 시간 범위 안
```

이 방식은 시간 구간 지정 여부와 관계없이 영상 전체를 한 번의 ffmpeg 호출로 처리하므로(구간은 select 필터 조건에 포함됨) `run_ffmpeg_with_progress()`로 실행되고, 진행률은 `report_progress(STEP_FRAME_EXTRACTION, ...)`로 보고됩니다. 추출된 timestamp는 FFmpeg `showinfo` 로그의 `pts_time`에서 읽습니다. 이미지 수와 timestamp 수가 맞지 않으면 `RuntimeError`가 발생합니다.

## 주요 구간 입력

전체 파이프라인에서는 STT 요약 결과의 `important_segments`를 사용해 프레임 추출 범위를 제한합니다.

```json
{
  "important_segments": [
    {"start": 10.0, "end": 30.0},
    {"start": 90.0, "end": 180.0}
  ]
}
```

`important_segments`가 문자열 JSON으로 들어와도 다시 파싱합니다. `start`, `end`가 없는 항목은 무시합니다.

구간 정규화 규칙:

- 시작 시간이 음수이면 `0.0`으로 보정합니다.
- 종료 시간이 시작 시간 이하인 구간은 제외합니다.
- 시작 시간 기준으로 정렬합니다.
- 겹치거나 맞닿은 구간은 병합합니다.

## 주요 함수

| 함수 | 설명 |
| --- | --- |
| `sample_frames()` | 실행 스크립트에서 호출하는 통합 함수(`max_frames_per_segment`는 representative에만 전달) |
| `sample_representative_frames()` | representative 방식 프레임 추출 |
| `sample_interval_frames()` | interval 방식 프레임 추출 |
| `sample_scene_change_frames()` | scene_change 방식 프레임 추출 |
| `load_important_time_ranges()` | LLM 요약 JSON에서 주요 구간 로드 |
| `load_frame_metadata()` | metadata JSON 읽기 |

메타데이터 JSON 저장/로드는 내부적으로 `modules.common.json_utils`의 `load_json()`/`save_json()`을 사용합니다.

### `sample_frames()`의 `project_root` 기본값

```python
project_root = Path(project_root) if project_root else run_dir.parent
```

`project_root`를 지정하지 않으면 `run_dir.parent`를 기준으로 `image_path`를 프로젝트 루트 상대 경로로 저장합니다. 표준 구조가 `project_root/runs`(`run_dir` 기본값이 `project_root/runs`)이므로 `run_dir`의 부모 한 단계만 올라가면 곧 프로젝트 루트입니다. (과거에는 `run_dir.parent.parent`로 두 단계를 올라가는 버그가 있어 `image_path`가 잘못된 상대 경로로 저장됐습니다.)

## 예외

| 상황 | 예외 |
| --- | --- |
| `interval_seconds <= 0` | `ValueError` |
| representative 후보 간격 `<= 0` 또는 구간당 최대 프레임 수 `< 1` | `ValueError` |
| scene threshold가 0과 1 사이가 아님 | `ValueError` |
| scene 최소 간격이 음수 | `ValueError` |
| 입력 영상 없음 | `FileNotFoundError` |
| scene/representative 후보 이미지 수와 timestamp 수 불일치 | `RuntimeError` |

같은 `run_dir`를 반복 사용하면 기존 `frame_*.jpg`가 삭제되고 새 결과로 대체됩니다.
