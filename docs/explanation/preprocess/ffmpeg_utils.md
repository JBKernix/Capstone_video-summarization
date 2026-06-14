# FFmpeg Utilities

## 개요

`modules/preprocess/ffmpeg_utils.py`는 FFmpeg와 FFprobe 실행을 공통으로 처리하는 유틸리티 모듈이다.

전처리 단계의 영상 정보 확인, 프레임 추출, 오디오 추출은 모두 이 모듈을 통해 외부 명령을 실행한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/ffmpeg_utils.py` | FFmpeg/FFprobe 실행 래퍼 |
| `modules/preprocess/video_info.py` | FFprobe로 영상 정보 추출 |
| `modules/preprocess/frame_sampler.py` | FFmpeg로 프레임 이미지 추출 |
| `modules/preprocess/audio_extractor.py` | FFmpeg로 오디오 추출 |

## 주요 책임

1. FFmpeg 명령 실행
2. FFprobe JSON 출력 파싱
3. `showinfo` timestamp 파싱
4. 기존 프레임 파일 정리

## 실행 흐름

```text
전처리 모듈
  -> run_ffmpeg() 또는 run_ffprobe_json()
      -> subprocess 실행
      -> stdout/stderr 수집
      -> 실패 시 예외 발생
```

## 주요 함수

### `run_ffmpeg()`

FFmpeg 명령을 실행한다.

호출자는 `ffmpeg` 실행 파일 이름을 제외한 인자 목록만 넘긴다.

예시:

```python
run_ffmpeg(["-y", "-i", "input.mp4", "output.wav"])
```

### `run_ffprobe_json()`

FFprobe를 실행하고 JSON 출력을 Python dict로 변환한다.

영상 길이, 해상도, FPS 같은 metadata를 얻을 때 사용한다.

### `remove_files()`

기존 추출 프레임을 삭제해 새 실행 결과와 섞이지 않도록 한다.

### `parse_showinfo_timestamps()`

화면 전환 방식에서 FFmpeg `showinfo` 로그의 `pts_time`을 추출한다.

## 예외 처리

FFmpeg나 FFprobe가 실패하면 예외가 발생하고, 호출한 단계가 중단된다.

대표 원인:

1. FFmpeg가 설치되어 있지 않음
2. 입력 파일 경로가 잘못됨
3. 지원하지 않는 영상 코덱
4. 출력 경로 권한 문제

## 주의 사항

1. FFmpeg 실행 파일이 PATH에 있어야 한다.
2. Windows에서는 경로에 공백이 있어도 인자 리스트 방식으로 넘기면 비교적 안전하다.
