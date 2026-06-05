# Video Info

## 개요

`modules/preprocess/video_info.py`는 FFprobe를 사용해 입력 영상의 기본 metadata를 읽는다.

프레임 추출 간격 계산, 로그 출력, 입력 검증에 필요한 정보를 제공한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/video_info.py` | 영상 metadata 추출 |
| `modules/preprocess/ffmpeg_utils.py` | FFprobe 실행 |
| `scripts/run_pipeline.py` | 전처리 단계에서 영상 정보 출력 |

## 주요 데이터 구조

### `VideoInfo`

```python
VideoInfo(
    path,
    duration,
    width,
    height,
    fps,
    frame_count,
    codec,
)
```

| 필드 | 설명 |
| --- | --- |
| `path` | 영상 파일 경로 |
| `duration` | 영상 길이, 초 단위 |
| `width` | 가로 해상도 |
| `height` | 세로 해상도 |
| `fps` | 초당 프레임 수 |
| `frame_count` | 전체 프레임 수. 없으면 `None` |
| `codec` | 비디오 코덱 이름 |

## 실행 흐름

```text
get_video_info(video_path)
  -> 입력 파일 존재 확인
  -> run_ffprobe_json()
  -> video stream 선택
  -> duration, resolution, fps, frame count 파싱
  -> VideoInfo 반환
```

## 주요 함수

### `get_video_info()`

입력 영상의 기본 정보를 반환한다.

FFprobe에서 다음 정보를 요청한다.

```text
format=duration
stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,duration
```

### `_parse_fraction()`

FFprobe의 FPS 값은 `30000/1001` 같은 분수 문자열로 올 수 있다.

`_parse_fraction()`은 이 값을 float로 바꾼다.

예시:

```text
30000/1001 -> 29.97002997
```

## 예외

| 상황 | 예외 |
| --- | --- |
| 영상 파일이 없음 | `FileNotFoundError` |
| 비디오 스트림이 없음 | `RuntimeError` |
| FFprobe 실행 실패 | FFprobe 실행 래퍼에서 예외 발생 |

## 주의 사항

1. 일부 영상은 `nb_frames`를 제공하지 않아 `frame_count`가 `None`일 수 있다.
2. FPS는 `avg_frame_rate` 기준이다.
3. duration은 format 정보가 우선이고, 없으면 stream duration을 사용한다.
