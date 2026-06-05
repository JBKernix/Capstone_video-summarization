# Frame Sampling

## 개요

`modules/preprocess/frame_sampler.py`는 입력 영상에서 대표 프레임 이미지를 추출하고, 각 프레임의 metadata를 JSON으로 저장한다.

vision 단계는 이 metadata를 읽어 각 프레임 이미지에 OCR을 수행한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/frame_sampler.py` | 프레임 추출과 metadata 생성 |
| `modules/preprocess/video_info.py` | 영상 정보 조회 |
| `modules/preprocess/ffmpeg_utils.py` | FFmpeg 실행, showinfo timestamp 파싱 |
| `scripts/run_preprocess.py` | 프레임 추출 단독 실행 |
| `scripts/run_pipeline.py` | 전체 파이프라인에서 프레임 추출 호출 |

## 출력 구조

기본 실행 결과:

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
    "timestamp": 0.0,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "interval"
  }
]
```

`image_path`는 프로젝트 루트 기준 상대경로로 저장된다.

## 주요 데이터 구조

### `FrameMetadata`

프레임 하나의 metadata를 표현하는 dataclass다.

| 필드 | 설명 |
| --- | --- |
| `frame_id` | 추출된 프레임 순번 |
| `timestamp` | 영상 내 시간, 초 단위 |
| `image_path` | 저장된 이미지 경로 |
| `sampling_method` | `interval` 또는 `scene_change` |

`to_dict()`는 JSON 저장 가능한 dict로 변환한다.

## 실행 흐름

```text
sample_frames()
  -> run_dir, frames_dir, metadata_path 결정
  -> method 확인
      -> interval이면 sample_interval_frames()
      -> scene_change이면 sample_scene_change_frames()
  -> frames/*.jpg 생성
  -> metadata/frame_metadata.json 생성
```

## 추출 방식

### 1. `interval`

일정 시간 간격으로 프레임을 추출한다.

```python
sample_interval_frames(
    video_path,
    frames_dir,
    metadata_path,
    interval_seconds=5.0,
)
```

FFmpeg 필터:

```text
fps=1/interval_seconds
```

예를 들어 `interval_seconds=5.0`이면 5초마다 한 장씩 추출한다.

timestamp는 추출 순번과 interval 값으로 계산한다.

```python
timestamp = index * interval_seconds
```

### 2. `scene_change`

장면 전환 정도를 기준으로 프레임을 추출한다.

```python
sample_scene_change_frames(
    video_path,
    frames_dir,
    metadata_path,
    threshold=0.35,
    min_scene_gap_seconds=1.0,
)
```

FFmpeg `select` 필터를 사용한다.

```text
select=gt(scene\,threshold)
```

`min_scene_gap_seconds`는 너무 가까운 장면 전환 프레임이 연속으로 선택되는 것을 줄이기 위한 최소 간격이다.

timestamp는 FFmpeg `showinfo` 로그에서 파싱한다.

## 주요 함수

### `_project_relative()`

저장된 이미지 경로를 프로젝트 루트 기준 상대경로로 변환한다.

프로젝트 루트 밖의 경로면 절대경로 문자열을 사용한다.

### `_write_metadata()`

`FrameMetadata` 목록을 JSON 파일로 저장한다.

```python
json.dump([item.to_dict() for item in metadata], f, ensure_ascii=False, indent=2)
```

### `load_frame_metadata()`

저장된 `frame_metadata.json`을 읽는다.

Windows BOM이 붙은 파일도 읽을 수 있도록 `utf-8-sig`를 사용한다.

### `get_sampling_summary()`

프레임 추출 전 참고용 영상 정보를 반환한다.

내부적으로 `get_video_info()`를 호출한다.

## 예외

| 상황 | 예외 |
| --- | --- |
| interval 값이 0 이하 | `ValueError` |
| scene threshold가 0과 1 사이가 아님 | `ValueError` |
| 입력 영상이 없음 | `FileNotFoundError` |
| 지원하지 않는 sampling method | `ValueError` |

## 주의 사항

1. 새 프레임 추출 전에 기존 `frame_*.jpg` 파일을 삭제한다.
2. 같은 `run_dir`을 반복 사용하면 이전 프레임과 metadata가 덮어써진다.
3. `scene_change` 방식은 영상 특성에 따라 추출 프레임 수가 크게 달라질 수 있다.
4. `interval` 방식은 예측 가능한 프레임 수를 얻기 쉽다.
