# Frame Sampling Pipeline

이 문서는 `modules/preprocess` 모듈이 영상에서 대표 프레임을 추출하고, 이후 vision 파이프라인에서 사용할 프레임 메타데이터를 생성하는 흐름을 설명한다. 현재 전처리 단계는 일정 시간 간격 프레임 추출과 장면 전환 기반 프레임 추출을 지원하며, 추출된 이미지 파일 경로와 영상 내 시간 정보를 `frame_metadata.json`으로 저장한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/frame_sampler.py` | 프레임 추출 방식 선택, 이미지 저장, 프레임 메타데이터 JSON 생성 |
| `modules/preprocess/video_info.py` | ffprobe를 사용해 영상 길이, 해상도, FPS, 프레임 수 등 기본 정보 추출 |
| `modules/preprocess/ffmpeg_utils.py` | ffmpeg/ffprobe 명령 실행, showinfo 로그에서 timestamp 파싱 |
| `runs/<run_name>/frames/` | 추출된 프레임 이미지 저장 위치 |
| `runs/<run_name>/metadata/frame_metadata.json` | vision 파이프라인 입력으로 사용할 프레임 메타데이터 |

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

## 1. `frame_sampler.py`

`frame_sampler.py`는 프레임 샘플링 단계의 중심 모듈이다. 영상 파일을 입력으로 받아 프레임 이미지를 저장하고, 저장된 이미지와 시간 정보를 메타데이터로 만든다.

### `FrameMetadata`

추출된 프레임 하나를 표현하는 데이터 클래스이다.

```python
@dataclass(frozen=True)
class FrameMetadata:
    frame_id: int
    timestamp: float
    image_path: str
    sampling_method: SamplingMethod
```

각 필드의 의미는 다음과 같다.

| 필드 | 의미 |
| --- | --- |
| `frame_id` | 추출된 프레임의 순번 |
| `timestamp` | 영상 내 프레임 시간. 단위는 초 |
| `image_path` | 저장된 프레임 이미지 경로 |
| `sampling_method` | 프레임 추출 방식. `interval` 또는 `scene_change` |

`to_dict()`는 이 데이터를 JSON으로 저장할 수 있는 딕셔너리로 변환한다.

### `sample_frames()`

전처리 단계에서 가장 먼저 호출하기 좋은 상위 함수이다. `run_dir` 구조에 맞춰 이미지 저장 위치와 메타데이터 저장 위치를 자동으로 정한다.

```python
sample_frames(
    video_path="data/input.mp4",
    run_dir="runs/sample",
    method="interval",
    interval_seconds=5.0,
    project_root=".",
)
```

내부에서 사용하는 경로는 다음과 같다.

```python
frames_dir = run_dir / "frames"
metadata_path = run_dir / "metadata" / "frame_metadata.json"
```

`method` 값에 따라 다음 함수 중 하나를 호출한다.

| method | 호출 함수 | 설명 |
| --- | --- | --- |
| `interval` | `sample_interval_frames()` | 일정 시간 간격으로 프레임 추출 |
| `scene_change` | `sample_scene_change_frames()` | 장면 전환으로 판단되는 프레임 추출 |

지원하지 않는 `method`가 들어오면 `ValueError`를 발생시킨다.

### `sample_interval_frames()`

일정 시간 간격으로 프레임을 추출한다. 예를 들어 `interval_seconds=5.0`이면 0초, 5초, 10초처럼 5초 간격으로 프레임을 저장한다.

ffmpeg에는 다음과 같은 방식으로 fps 필터를 전달한다.

```python
fps_value = 1.0 / interval_seconds

run_ffmpeg([
    "-y",
    "-i", str(video_path),
    "-vf", f"fps={fps_value}",
    "-q:v", "2",
    str(output_pattern),
])
```

저장되는 이미지 파일명은 다음 형식이다.

```text
frame_000001.jpg
frame_000002.jpg
frame_000003.jpg
```

프레임 시간은 추출 순서와 간격을 기준으로 계산한다.

```python
timestamp = round(index * interval_seconds, 3)
```

처리가 끝나면 다음과 같은 메시지를 출력한다.

```text
프레임 메타데이터 저장 완료: runs/sample/metadata/frame_metadata.json
일정 간격 프레임 추출 완료. 추출 프레임 수: 3
```

### `sample_scene_change_frames()`

장면 전환이 발생했다고 판단되는 프레임을 추출한다. 이 방식은 ffmpeg의 `scene` 필터를 사용한다.

```python
select=gt(scene\,0.35)
```

`threshold` 값이 낮을수록 더 많은 프레임이 선택되고, 높을수록 변화가 큰 장면만 선택된다. 기본값은 `0.35`이다.

너무 가까운 장면 전환 프레임이 연속으로 저장되는 것을 줄이기 위해 `min_scene_gap_seconds`를 사용한다. 기본값은 1초이다.

```python
if(isnan(prev_selected_t)\,1\,gte(t-prev_selected_t\,1.0))
```

장면 전환 방식에서는 ffmpeg `showinfo` 로그에서 실제 선택된 프레임의 timestamp를 읽는다.

```python
timestamps = parse_showinfo_timestamps(result.stderr)
```

처리가 끝나면 다음과 같은 메시지를 출력한다.

```text
프레임 메타데이터 저장 완료: runs/sample/metadata/frame_metadata.json
장면 전환 프레임 추출 완료. 추출 프레임 수: 2
```

### `load_frame_metadata()`

생성된 `frame_metadata.json` 파일을 다시 읽어 리스트로 반환한다.

```python
frames_metadata = load_frame_metadata("runs/sample/metadata/frame_metadata.json")
```

Windows 환경에서 UTF-8 BOM이 붙은 JSON도 읽을 수 있도록 `utf-8-sig`를 사용한다.

```python
with Path(metadata_path).open("r", encoding="utf-8-sig") as f:
    return json.load(f)
```

### `get_sampling_summary()`

프레임 추출 전에 영상 기본 정보를 확인할 때 사용하는 함수이다. 내부적으로 `get_video_info()`를 호출하고 딕셔너리로 변환한다.

```python
summary = get_sampling_summary("data/input.mp4")
```

반환 예시는 다음과 같다.

```json
{
  "path": "data/input.mp4",
  "duration": 120.0,
  "width": 1920,
  "height": 1080,
  "fps": 30.0,
  "frame_count": 3600,
  "codec": "h264"
}
```

## 2. `video_info.py`

`video_info.py`는 ffprobe를 사용해 영상 파일의 기본 메타데이터를 읽는다.

### `VideoInfo`

영상 정보를 담는 데이터 클래스이다.

| 필드 | 의미 |
| --- | --- |
| `path` | 영상 파일 경로 |
| `duration` | 영상 길이. 단위는 초 |
| `width` | 영상 가로 해상도 |
| `height` | 영상 세로 해상도 |
| `fps` | 초당 프레임 수 |
| `frame_count` | 전체 프레임 수. ffprobe가 제공하지 않으면 `None` |
| `codec` | 영상 코덱 이름 |

### `get_video_info()`

영상 파일에서 첫 번째 비디오 스트림 정보를 읽는다.

```python
info = get_video_info("data/input.mp4")
```

ffprobe에는 다음 정보를 요청한다.

```text
format=duration
stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,duration
```

FPS는 ffprobe가 `30/1`, `30000/1001` 같은 분수 문자열로 반환할 수 있기 때문에 `_parse_fraction()`에서 실수로 변환한다.

```python
fps = _parse_fraction(stream.get("avg_frame_rate"))
```

영상 파일이 없으면 `FileNotFoundError`, 영상 스트림을 찾을 수 없으면 `RuntimeError`를 발생시킨다.

## 3. `ffmpeg_utils.py`

`ffmpeg_utils.py`는 외부 명령 실행과 로그 파싱을 공통으로 처리한다.

### `ensure_command()`

`ffmpeg`, `ffprobe` 같은 실행 파일이 PATH에 등록되어 있는지 확인한다.

```python
resolved = shutil.which(command)
```

실행 파일을 찾지 못하면 다음 예외를 발생시킨다.

```text
필수 실행 파일을 찾을 수 없습니다: ffmpeg
```

### `run_command()`

명령어를 실행하고 표준 출력과 표준 오류를 문자열로 받아온다.

```python
subprocess.run(
    list(args),
    check=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
```

`check=True`를 사용하기 때문에 명령 실행이 실패하면 `subprocess.CalledProcessError`가 발생한다.

### `run_ffmpeg()`

`ffmpeg` 실행 파일 경로를 확인한 뒤 전달받은 인자를 붙여 실행한다.

```python
return run_command([ensure_command("ffmpeg"), *args])
```

### `run_ffprobe_json()`

`ffprobe`를 JSON 출력 모드로 실행하고, 결과를 딕셔너리로 변환한다.

```python
return json.loads(result.stdout)
```

### `parse_showinfo_timestamps()`

장면 전환 프레임 추출에서 사용한다. ffmpeg `showinfo` 로그에 포함된 `pts_time` 값을 정규식으로 찾는다.

```python
SHOWINFO_TIME_PATTERN = re.compile(r"pts_time:(?P<time>[0-9]+(?:\.[0-9]+)?)")
```

예를 들어 로그에 `pts_time:12.345`가 있으면 `12.345`를 float 값으로 추출한다.

### `remove_files()`

프레임을 새로 추출하기 전에 기존 이미지 파일을 지울 때 사용한다. 같은 `image_prefix`를 가진 파일만 삭제하므로 다른 결과 파일에는 영향을 주지 않는다.

```python
remove_files(frames_dir.glob(f"{image_prefix}_*.jpg"))
```

## 입력 파일 형식

프레임 샘플링 단계의 입력은 영상 파일이다.

```text
data/input.mp4
```

현재 구현은 첫 번째 비디오 스트림을 기준으로 동작한다. 오디오 스트림은 프레임 추출에 사용하지 않는다.

## 출력 파일 형식

프레임 샘플링 결과는 이미지 파일과 메타데이터 JSON으로 나뉜다.

```text
runs/sample/frames/frame_000001.jpg
runs/sample/frames/frame_000002.jpg
runs/sample/metadata/frame_metadata.json
```

`frame_metadata.json`은 프레임 목록을 담은 JSON 배열이다.

```json
[
  {
    "frame_id": 0,
    "timestamp": 0.0,
    "image_path": "runs/sample/frames/frame_000001.jpg",
    "sampling_method": "interval"
  },
  {
    "frame_id": 1,
    "timestamp": 5.0,
    "image_path": "runs/sample/frames/frame_000002.jpg",
    "sampling_method": "interval"
  }
]
```

| 필드 | 의미 |
| --- | --- |
| `frame_id` | 추출된 프레임의 순번 |
| `timestamp` | 영상 내 프레임 시간. 단위는 초 |
| `image_path` | vision 파이프라인에서 OCR을 수행할 이미지 경로 |
| `sampling_method` | 프레임 추출 방식 |

이 메타데이터는 이후 `modules/vision/vision_formatter.py`의 `analyze_frames_metadata()`에서 입력으로 사용된다.

## 실패 처리

영상 파일이 없으면 즉시 `FileNotFoundError`를 발생시킨다.

```python
if not video_path.exists():
    raise FileNotFoundError(...)
```

프레임 추출 간격이 0 이하이면 `ValueError`를 발생시킨다.

```python
if interval_seconds <= 0:
    raise ValueError(...)
```

장면 전환 임계값은 0과 1 사이 값이어야 한다.

```python
if not 0 < threshold < 1:
    raise ValueError(...)
```

ffmpeg 또는 ffprobe 실행이 실패하면 `subprocess.CalledProcessError`가 발생한다. 이 경우 외부 실행 파일 설치 상태, 입력 영상 경로, 코덱 지원 여부를 확인해야 한다.

## 현재 한계

현재 프레임 샘플링 단계는 ffmpeg 기반 규칙으로 동작한다.

주요 한계는 다음과 같다.

1. 일정 간격 추출의 timestamp는 실제 저장된 프레임의 원본 PTS가 아니라 `index * interval_seconds`로 계산한다.
2. 장면 전환 추출은 ffmpeg `scene` 점수에 의존하므로 화면 변화가 작지만 의미가 큰 장면은 놓칠 수 있다.
3. `threshold` 값에 따라 프레임 수가 크게 달라질 수 있어 영상 종류에 맞는 튜닝이 필요하다.
4. 기존 프레임을 새로 추출할 때 같은 prefix의 이미지 파일을 삭제하므로, 같은 디렉터리에 여러 샘플링 결과를 함께 저장하려면 prefix를 다르게 지정해야 한다.

이 구조는 이후 OCR, 이미지 캡션, 요약 단계가 사용할 대표 프레임 목록을 만드는 기본 전처리 단계로 볼 수 있다.