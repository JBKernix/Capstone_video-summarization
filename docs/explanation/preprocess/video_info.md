# Video Info Pipeline

이 문서는 `modules/preprocess/video_info.py`가 ffprobe를 사용해 영상의 기본 정보를 읽는 흐름을 설명한다. 이 정보는 전처리 단계에서 입력 영상이 정상적인지 확인하고, 프레임 샘플링 결과를 해석할 때 참고하는 메타데이터로 사용된다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/video_info.py` | 영상 길이, 해상도, FPS, 프레임 수, 코덱 정보 추출 |
| `modules/preprocess/ffmpeg_utils.py` | ffprobe 실행과 JSON 파싱 공통 처리 |
| `scripts/run_preprocess.py` | 전처리 실행 전에 영상 정보를 출력 |
| `modules/preprocess/frame_sampler.py` | `get_sampling_summary()`에서 영상 정보 조회 |

## 전체 실행 흐름

```text
get_video_info()
    -> 입력 영상 경로를 Path 객체로 변환
    -> 파일 존재 여부 확인
    -> run_ffprobe_json()으로 첫 번째 비디오 스트림 조회
    -> streams 배열이 비어 있으면 예외 발생
    -> duration, width, height, fps, frame_count, codec 추출
    -> VideoInfo 객체로 반환
```

## 1. `VideoInfo`

`VideoInfo`는 영상 기본 정보를 담는 불변 데이터 클래스다.

```python
@dataclass(frozen=True)
class VideoInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    frame_count: Optional[int]
    codec: Optional[str]
```

| 필드 | 의미 |
| --- | --- |
| `path` | 영상 파일 경로 |
| `duration` | 영상 길이. 단위는 초 |
| `width` | 영상 가로 해상도 |
| `height` | 영상 세로 해상도 |
| `fps` | 초당 프레임 수 |
| `frame_count` | 전체 프레임 수. ffprobe가 제공하지 않으면 `None` |
| `codec` | 비디오 코덱 이름 |

### `to_dict()`

`VideoInfo` 객체를 딕셔너리로 변환한다.

```python
info = get_video_info("data/input/video.mp4")
info_dict = info.to_dict()
```

반환 예시는 다음과 같다.

```json
{
  "path": "data/input/video.mp4",
  "duration": 120.0,
  "width": 1920,
  "height": 1080,
  "fps": 29.97,
  "frame_count": 3596,
  "codec": "h264"
}
```

## 2. `_parse_fraction()`

ffprobe는 FPS를 `30/1`, `30000/1001` 같은 분수 문자열로 반환할 수 있다. `_parse_fraction()`은 이 값을 실수로 변환한다.

| 입력 | 반환 |
| --- | --- |
| `"30/1"` | `30.0` |
| `"30000/1001"` | 약 `29.97` |
| `"0/0"` | `0.0` |
| `None` | `0.0` |

## 3. `get_video_info()`

영상에서 첫 번째 비디오 스트림의 정보를 읽는다.

```python
info = get_video_info("data/input/video.mp4")
```

ffprobe에는 다음 항목을 요청한다.

```text
format=duration
stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,duration
```

현재 구현은 `-select_streams v:0` 옵션을 사용하므로 첫 번째 비디오 스트림만 대상으로 한다.

```python
data = run_ffprobe_json([
    "-show_entries",
    "format=duration:stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,duration",
    "-select_streams",
    "v:0",
    str(video_path),
])
```

영상 길이는 우선 `format.duration`을 사용하고, 없으면 스트림의 `duration`을 사용한다.

```python
duration_text = format_info.get("duration") or stream.get("duration") or "0"
```

프레임 수는 `nb_frames`가 숫자 문자열일 때만 정수로 변환한다. 값이 없거나 숫자가 아니면 `None`으로 둔다.

## 실패 처리

영상 파일이 없으면 `FileNotFoundError`가 발생한다.

ffprobe 결과에 비디오 스트림이 없으면 `RuntimeError`가 발생한다.

ffprobe 실행 자체가 실패하면 `subprocess.CalledProcessError`가 발생한다.

## 현재 한계

1. 여러 비디오 스트림이 있는 파일에서는 첫 번째 비디오 스트림만 사용한다.
2. `nb_frames`가 제공되지 않는 컨테이너에서는 전체 프레임 수가 `None`이 될 수 있다.
3. FPS가 가변 프레임레이트 영상의 실제 시간 흐름을 완전히 설명하지는 못한다.