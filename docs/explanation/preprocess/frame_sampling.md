# 프레임 샘플링

`modules/preprocess/frame_sampler.py`는 영상에서 JPG 프레임을 추출하고 `frame_metadata.json`을 생성합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/frame_sampler.py` | interval/scene_change 샘플링 구현 |
| `modules/preprocess/video_info.py` | 영상 정보 조회 |
| `modules/preprocess/ffmpeg_utils.py` | FFmpeg 실행과 showinfo timestamp 파싱 |
| `scripts/run_preprocess.py` | 프레임 샘플링 단독 실행 |
| `scripts/run_pipeline.py` | STT 요약 이후 주요 구간 샘플링 호출 |

## 기본값

```python
DEFAULT_SAMPLING_METHOD = "interval"
DEFAULT_INTERVAL_SECONDS = 5.0
DEFAULT_SCENE_THRESHOLD = 0.5
DEFAULT_SCENE_MIN_GAP_SECONDS = 1.0
```

지원하는 방식은 `interval`, `scene_change`입니다.

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
    "sampling_method": "interval"
  }
]
```

## 실행 흐름

```text
sample_frames()
  -> important_segments_path가 있으면 load_important_time_ranges()
  -> method 확인
      -> interval: sample_interval_frames()
      -> scene_change: sample_scene_change_frames()
  -> runs/frames/frame_*.jpg 생성
  -> runs/metadata/frame_metadata.json 저장
```

## interval 방식

전체 영상 또는 지정된 시간 구간에서 일정 간격으로 프레임을 추출합니다.

```bash
python scripts/run_preprocess.py --method interval --interval-seconds 5
```

시간 구간이 있으면 각 구간의 시작점부터 종료점까지 `interval_seconds` 간격으로 timestamp를 만듭니다. 중복 timestamp는 제거합니다.

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

추출된 timestamp는 FFmpeg `showinfo` 로그의 `pts_time`에서 읽습니다. 이미지 수와 timestamp 수가 맞지 않으면 `RuntimeError`가 발생합니다.

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
| `sample_frames()` | 실행 스크립트에서 호출하는 통합 함수 |
| `sample_interval_frames()` | interval 방식 프레임 추출 |
| `sample_scene_change_frames()` | scene_change 방식 프레임 추출 |
| `load_important_time_ranges()` | LLM 요약 JSON에서 주요 구간 로드 |
| `load_frame_metadata()` | metadata JSON 읽기 |
| `get_sampling_summary()` | 샘플링 전 영상 정보 조회 |

## 예외

| 상황 | 예외 |
| --- | --- |
| `interval_seconds <= 0` | `ValueError` |
| scene threshold가 0과 1 사이가 아님 | `ValueError` |
| scene 최소 간격이 음수 | `ValueError` |
| 입력 영상 없음 | `FileNotFoundError` |
| scene 이미지 수와 timestamp 수 불일치 | `RuntimeError` |

같은 `run_dir`를 반복 사용하면 기존 `frame_*.jpg`가 삭제되고 새 결과로 대체됩니다.
