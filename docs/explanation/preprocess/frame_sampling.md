# Frame Sampling Pipeline

이 문서는 `modules/preprocess/frame_sampler.py`가 영상에서 대표 프레임을 추출하고, 이후 vision 파이프라인에서 사용할 `frame_metadata.json`을 생성하는 흐름을 설명한다. 현재 구현은 일정 시간 간격 기반 추출과 장면 전환 기반 추출을 지원한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/frame_sampler.py` | 프레임 추출 방식 선택, 이미지 저장, 프레임 메타데이터 생성 |
| `modules/preprocess/video_info.py` | 영상 길이, 해상도, FPS, 프레임 수 등 기본 정보 추출 |
| `modules/preprocess/ffmpeg_utils.py` | ffmpeg/ffprobe 명령 실행, showinfo 로그 timestamp 파싱 |
| `scripts/run_preprocess.py` | CLI에서 프레임 샘플링 실행 |
| `runs/frames/` | 추출된 프레임 이미지 저장 위치 |
| `runs/metadata/frame_metadata.json` | vision 파이프라인 입력으로 사용할 프레임 메타데이터 |

## 전체 실행 흐름

```text
sample_frames()
    -> run_dir 기준으로 frames 디렉터리와 metadata 경로 설정
    -> method 값 확인
        -> interval
            -> sample_interval_frames()
                -> ffmpeg fps 필터로 일정 간격 프레임 추출
                -> frame_000001.jpg 형식으로 이미지 저장
                -> frame_id, timestamp, image_path, sampling_method 생성
                -> frame_metadata.json 저장
        -> scene_change
            -> sample_scene_change_frames()
                -> ffmpeg scene select 필터로 장면 전환 프레임 추출
                -> showinfo 로그에서 실제 timestamp 파싱
                -> frame_id, timestamp, image_path, sampling_method 생성
                -> frame_metadata.json 저장
```

## 1. `FrameMetadata`

추출된 프레임 하나를 표현하는 데이터 클래스다.

```python
@dataclass(frozen=True)
class FrameMetadata:
    frame_id: int
    timestamp: float
    image_path: str
    sampling_method: SamplingMethod
```

| 필드 | 의미 |
| --- | --- |
| `frame_id` | 추출된 프레임의 순번 |
| `timestamp` | 영상 안에서 해당 프레임의 시간. 단위는 초 |
| `image_path` | 저장된 프레임 이미지 경로 |
| `sampling_method` | 프레임 추출 방식. `interval` 또는 `scene_change` |

### `to_dict()`

`FrameMetadata` 객체를 JSON 저장 가능한 딕셔너리로 변환한다.

```python
metadata_item.to_dict()
```

반환 예시는 다음과 같다.

```json
{
  "frame_id": 0,
  "timestamp": 0.0,
  "image_path": "runs/frames/frame_000001.jpg",
  "sampling_method": "interval"
}
```

## 2. `_project_relative()`

프레임 이미지 경로를 프로젝트 루트 기준 상대 경로로 변환한다.

```python
image_path=_project_relative(image_path, project_root)
```

`path`가 `project_root` 내부에 있으면 상대 경로를 반환하고, 그렇지 않으면 절대 경로를 POSIX 형식 문자열로 반환한다.

## 3. `_write_metadata()`

프레임 메타데이터 목록을 JSON 파일로 저장한다.

```python
_write_metadata(metadata, metadata_path)
```

저장 전에 metadata 디렉터리를 자동으로 생성한다.

```python
metadata_path.parent.mkdir(parents=True, exist_ok=True)
```

JSON 저장 시 `ensure_ascii=False`를 사용하므로 한글이 들어가도 이스케이프되지 않는다.

```python
json.dump([item.to_dict() for item in metadata], f, ensure_ascii=False, indent=2)
```

## 4. `sample_interval_frames()`

일정 시간 간격으로 프레임을 추출한다. 예를 들어 `interval_seconds=5.0`이면 0초, 5초, 10초처럼 5초 간격의 프레임을 저장한다.

```python
sample_interval_frames(
    video_path="data/input/video.mp4",
    frames_dir="runs/frames",
    metadata_path="runs/metadata/frame_metadata.json",
    interval_seconds=5.0,
    project_root=".",
)
```

### 입력 검증

프레임 추출 간격은 0보다 커야 한다.

```python
if interval_seconds <= 0:
    raise ValueError(...)
```

입력 영상 파일이 없으면 `FileNotFoundError`가 발생한다.

### 기존 프레임 정리

같은 prefix를 가진 기존 이미지 파일을 삭제한 뒤 새로 추출한다.

```python
remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))
```

기본 prefix는 `frame`이므로 다음 파일들이 정리 대상이다.

```text
frame_000001.jpg
frame_000002.jpg
```

### ffmpeg 실행

일정 간격 추출은 ffmpeg의 `fps` 필터를 사용한다.

```python
fps_value = 1.0 / interval_seconds
```

```python
run_ffmpeg([
    "-y",
    "-i", str(video_path),
    "-vf", f"fps={fps_value}",
    "-q:v", "2",
    str(output_pattern),
])
```

이미지 파일은 다음 형식으로 저장된다.

```text
frame_000001.jpg
frame_000002.jpg
frame_000003.jpg
```

### timestamp 계산

일정 간격 방식에서는 실제 ffmpeg 로그를 읽지 않고 추출 순서와 간격을 기반으로 timestamp를 계산한다.

```python
timestamp = round(index * interval_seconds, 3)
```

## 5. `sample_scene_change_frames()`

장면 전환으로 판단되는 프레임을 추출한다. 영상의 변화량이 큰 지점을 대표 프레임으로 선택할 때 사용한다.

```python
sample_scene_change_frames(
    video_path="data/input/video.mp4",
    frames_dir="runs/frames",
    metadata_path="runs/metadata/frame_metadata.json",
    threshold=0.35,
    project_root=".",
    min_scene_gap_seconds=1.0,
)
```

### 입력 검증

`threshold`는 0과 1 사이 값이어야 한다.

```python
if not 0 < threshold < 1:
    raise ValueError(...)
```

`min_scene_gap_seconds`는 0 이상이어야 한다.

```python
if min_scene_gap_seconds < 0:
    raise ValueError(...)
```

### scene 필터

장면 전환 추출은 ffmpeg의 `scene` 값을 사용한다.

```text
select=gt(scene\,0.35)
```

`threshold`가 낮을수록 더 많은 프레임이 선택되고, 높을수록 변화가 큰 장면만 선택된다.

너무 가까운 장면 전환 프레임이 연속으로 저장되는 것을 줄이기 위해 `min_scene_gap_seconds`를 적용한다.

```text
if(isnan(prev_selected_t)\,1\,gte(t-prev_selected_t\,1.0))
```

### ffmpeg 실행

장면 전환 방식에서는 `showinfo`를 함께 사용해 선택된 프레임의 실제 timestamp를 stderr 로그에 남긴다.

```python
result = run_ffmpeg([
    "-y",
    "-i", str(video_path),
    "-vf", f"{select_filter},showinfo",
    "-vsync", "vfr",
    "-q:v", "2",
    str(output_pattern),
])
```

이후 `parse_showinfo_timestamps()`로 `pts_time` 값을 읽는다.

```python
timestamps = parse_showinfo_timestamps(result.stderr)
```

timestamp가 이미지 개수보다 적게 파싱된 경우에는 fallback으로 `0.0`을 사용한다.

```python
timestamp=round(timestamps[index], 3) if index < len(timestamps) else 0.0
```

## 6. `sample_frames()`

전처리 단계에서 호출하기 좋은 상위 함수다. `run_dir` 구조에 맞춰 프레임 디렉터리와 메타데이터 경로를 자동으로 정한다.

```python
sample_frames(
    video_path="data/input/video.mp4",
    run_dir="runs",
    method="interval",
    interval_seconds=5.0,
    scene_threshold=0.35,
    project_root=".",
)
```

내부 경로는 다음과 같이 만들어진다.

```python
frames_dir = run_dir / "frames"
metadata_path = run_dir / "metadata" / "frame_metadata.json"
```

`method` 값에 따라 호출 함수가 달라진다.

| method | 호출 함수 | 설명 |
| --- | --- | --- |
| `interval` | `sample_interval_frames()` | 일정 시간 간격으로 프레임 추출 |
| `scene_change` | `sample_scene_change_frames()` | 장면 전환 기준으로 프레임 추출 |

지원하지 않는 `method`가 들어오면 `ValueError`가 발생한다.

## 7. `load_frame_metadata()`

생성된 `frame_metadata.json` 파일을 다시 읽어 리스트로 반환한다.

```python
frames_metadata = load_frame_metadata("runs/metadata/frame_metadata.json")
```

Windows 환경에서 UTF-8 BOM이 붙은 JSON도 읽을 수 있도록 `utf-8-sig`를 사용한다.

```python
with Path(metadata_path).open("r", encoding="utf-8-sig") as f:
    return json.load(f)
```

## 8. `get_sampling_summary()`

프레임 추출 전에 영상 기본 정보를 확인하기 위한 보조 함수다. 내부적으로 `get_video_info()`를 호출하고 딕셔너리로 변환한다.

```python
summary = get_sampling_summary("data/input/video.mp4")
```

반환 예시는 다음과 같다.

```json
{
  "path": "data/input/video.mp4",
  "duration": 120.0,
  "width": 1920,
  "height": 1080,
  "fps": 30.0,
  "frame_count": 3600,
  "codec": "h264"
}
```

## 입력 파일 형식

입력은 ffmpeg가 읽을 수 있는 영상 파일이다.

```text
data/input/video.mp4
```

현재 구현은 첫 번째 비디오 스트림을 기준으로 동작한다. 오디오 스트림은 프레임 추출에는 사용하지 않는다.

## 출력 파일 형식

프레임 샘플링 결과는 이미지 파일과 JSON 메타데이터로 나뉜다.

```text
runs/frames/frame_000001.jpg
runs/frames/frame_000002.jpg
runs/metadata/frame_metadata.json
```

`frame_metadata.json`은 프레임 목록을 담은 JSON 배열이다.

```json
[
  {
    "frame_id": 0,
    "timestamp": 0.0,
    "image_path": "runs/frames/frame_000001.jpg",
    "sampling_method": "interval"
  },
  {
    "frame_id": 1,
    "timestamp": 5.0,
    "image_path": "runs/frames/frame_000002.jpg",
    "sampling_method": "interval"
  }
]
```

이 메타데이터는 이후 vision 단계에서 어떤 이미지가 몇 초 지점의 프레임인지 알기 위해 사용된다.

## 실패 처리

입력 영상 파일이 없으면 `FileNotFoundError`가 발생한다.

프레임 추출 간격이 0 이하이면 `ValueError`가 발생한다.

장면 전환 임계값이 0과 1 사이가 아니면 `ValueError`가 발생한다.

ffmpeg 실행이 실패하면 `subprocess.CalledProcessError`가 발생한다. 이 경우 ffmpeg 설치 상태, 입력 영상 경로, 코덱 지원 여부를 확인해야 한다.

## 현재 한계

1. 일정 간격 추출의 timestamp는 실제 저장된 프레임의 원본 PTS가 아니라 `index * interval_seconds`로 계산한다.
2. 장면 전환 추출은 ffmpeg의 `scene` 값에 의존하므로 화면 변화가 작지만 의미 있는 장면은 놓칠 수 있다.
3. `threshold` 값에 따라 프레임 수가 크게 달라지므로 영상 종류에 맞는 조정이 필요하다.
4. 기존 프레임을 새로 추출할 때 같은 prefix의 이미지 파일만 삭제하므로, 여러 샘플링 결과를 같은 디렉터리에 섞어 저장하려면 prefix 관리가 필요하다.