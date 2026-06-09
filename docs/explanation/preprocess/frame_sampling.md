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
    interval_000001.jpg
    scene_000001.jpg
  metadata/
    frame_metadata.json
```

metadata 예시:

```json
[
  {
    "frame_id": 0,
    "timestamp": 0.0,
    "image_path": "runs/frames/interval_000001.jpg",
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
      -> interval_scene_change이면 sample_interval_scene_change_frames()
  -> frames/*.jpg 생성
  -> metadata/frame_metadata.json 생성
```

## 추출 방식

기본 추출 방식은 `interval_scene_change`다. 기본 interval은 `60.0`초, 기본 scene threshold는 `0.35`다.

### 1. `interval`

일정 시간 간격으로 프레임을 추출한다.

```python
sample_interval_frames(
    video_path,
    frames_dir,
    metadata_path,
    interval_seconds=60.0,
)
```

FFmpeg 필터:

```text
fps=1/interval_seconds
```

예를 들어 `interval_seconds=60.0`이면 60초마다 한 장씩 추출한다.

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

### 3. `interval_scene_change`

일정 간격 프레임을 기본으로 추출하고, 장면 전환 프레임을 추가로 보강한다.

```python
sample_interval_scene_change_frames(
    video_path,
    frames_dir,
    metadata_path,
    interval_seconds=60.0,
    scene_threshold=0.35,
    min_gap_seconds=1.0,
)
```

처리 순서:

```text
기존 frame_*.jpg, interval_*.jpg, scene_*.jpg 삭제
  -> interval_*.jpg 추출
  -> scene_*.jpg 추출
  -> 가까운 중복 프레임 병합
  -> frame_id를 timestamp 순서로 다시 부여
  -> metadata/frame_metadata.json 최종 저장
```

`min_gap_seconds`보다 가까운 프레임은 중복으로 보고 하나만 남긴다. 같은 시간대에 `interval`과 `scene_change`가 함께 있으면 `scene_change` 프레임을 우선한다.

## 주요 함수

### `_project_relative()`

저장된 이미지 경로를 프로젝트 루트 기준 상대경로로 변환한다.

프로젝트 루트 밖의 경로면 절대경로 문자열을 사용한다.

### `_write_metadata()`

`FrameMetadata` 목록을 JSON 파일로 저장한다.

```python
json.dump([item.to_dict() for item in metadata], f, ensure_ascii=False, indent=2)
```

### `_merge_frame_metadata()`

`interval_scene_change` 방식에서 interval 결과와 scene_change 결과를 합친다.

가까운 중복을 제거한 뒤 timestamp 순서로 정렬하고 `frame_id`를 다시 부여한다.

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
| 병합 최소 간격이 0 미만 | `ValueError` |
| 입력 영상이 없음 | `FileNotFoundError` |
| 지원하지 않는 sampling method | `ValueError` |

## 주의 사항

1. 새 프레임 추출 전에 해당 방식의 기존 프레임 파일을 삭제한다.
2. 같은 `run_dir`을 반복 사용하면 이전 프레임과 metadata가 덮어써진다.
3. `scene_change` 방식은 영상 특성에 따라 추출 프레임 수가 크게 달라질 수 있다.
4. `interval` 방식은 예측 가능한 프레임 수를 얻기 쉽다.
5. `interval_scene_change` 방식은 `interval_*.jpg`와 `scene_*.jpg`를 함께 만들며, 최종 metadata는 병합 결과만 담는다.
