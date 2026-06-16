# 영상 정보 조회

`modules/preprocess/video_info.py`는 FFprobe를 사용해 영상 길이, 해상도, FPS, 코덱 정보를 읽습니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/video_info.py` | `VideoInfo`와 `get_video_info()` |
| `modules/preprocess/ffmpeg_utils.py` | FFprobe 실행 |
| `scripts/run_pipeline.py` | 로그 출력과 전처리 검증 |
| `scripts/run_preprocess.py` | 전처리 단독 실행 |

## 데이터 구조

```python
VideoInfo(
    path="data/input/sample.mp4",
    duration=120.5,
    width=1920,
    height=1080,
    fps=29.97,
    frame_count=3610,
    codec="h264",
)
```

| 필드 | 설명 |
| --- | --- |
| `path` | 영상 파일 경로 |
| `duration` | 영상 길이, 초 단위 |
| `width` | 가로 해상도 |
| `height` | 세로 해상도 |
| `fps` | 초당 프레임 수 |
| `frame_count` | 전체 프레임 수, 없으면 `None` |
| `codec` | 영상 코덱 이름 |

## 실행 흐름

```text
get_video_info(video_path)
  -> 입력 파일 존재 확인
  -> ffprobe JSON 요청
  -> 첫 번째 video stream 선택
  -> duration, resolution, fps, frame_count, codec 파싱
  -> VideoInfo 반환
```

## FFprobe 요청 필드

```text
format=duration
stream=index,codec_type,codec_name,width,height,avg_frame_rate,nb_frames,duration
```

FPS는 `avg_frame_rate`가 `30000/1001` 같은 분수 문자열로 올 수 있어 `Fraction`으로 float 변환합니다.

## 예외

| 상황 | 예외 |
| --- | --- |
| 영상 파일 없음 | `FileNotFoundError` |
| 비디오 스트림 없음 | `RuntimeError` |
| FFprobe 실행 실패 | `subprocess.CalledProcessError` |

## 주의 사항

- 일부 영상은 `nb_frames`를 제공하지 않아 `frame_count`가 `None`일 수 있습니다.
- duration은 format duration을 우선 사용하고, 없으면 stream duration을 사용합니다.
