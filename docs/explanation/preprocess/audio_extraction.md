# Audio Extraction

## 개요

`modules/preprocess/audio_extractor.py`는 입력 영상에서 STT에 사용할 오디오 파일을 추출한다.

기본 출력은 Whisper가 처리하기 쉬운 16kHz mono WAV 파일이다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/audio_extractor.py` | 영상에서 WAV 오디오 추출 |
| `modules/preprocess/ffmpeg_utils.py` | FFmpeg 실행 래퍼 |
| `scripts/run_pipeline.py` | 전체 파이프라인에서 오디오 추출 호출 |

## 실행 흐름

```text
run_audio_step()
  -> extract_audio()
      -> 입력 영상 경로 확인
      -> 출력 디렉터리 생성
      -> FFmpeg 인자 구성
      -> run_ffmpeg()
      -> runs/audio/audio.wav 반환
```

## 주요 함수

### `extract_audio()`

```python
extract_audio(
    video_path,
    audio_path,
    sample_rate=16000,
    channels=1,
    overwrite=True,
)
```

| 인자 | 설명 |
| --- | --- |
| `video_path` | 원본 영상 경로 |
| `audio_path` | 저장할 WAV 경로 |
| `sample_rate` | 출력 sample rate. 기본값 `16000` |
| `channels` | 출력 채널 수. 기본값 `1` |
| `overwrite` | 기존 파일 덮어쓰기 여부 |

## FFmpeg 명령 구조

생성되는 FFmpeg 인자는 개념적으로 다음과 같다.

```text
ffmpeg -y -i input.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 runs/audio/audio.wav
```

| 옵션 | 의미 |
| --- | --- |
| `-y` | 기존 파일 덮어쓰기 |
| `-i` | 입력 파일 |
| `-vn` | 비디오 스트림 제외 |
| `-acodec pcm_s16le` | WAV PCM 인코딩 |
| `-ar 16000` | 16kHz sample rate |
| `-ac 1` | mono 채널 |

## 출력

전체 파이프라인 기본 출력:

```text
runs/audio/audio.wav
```

## 예외

| 상황 | 예외 |
| --- | --- |
| 입력 영상이 없음 | `FileNotFoundError` |
| FFmpeg 실행 실패 | `subprocess.CalledProcessError` |

## 주의 사항

1. FFmpeg가 시스템에서 실행 가능해야 한다.
2. 오디오가 없는 영상이면 FFmpeg 단계에서 실패할 수 있다.
3. STT 품질을 위해 16kHz mono WAV로 통일한다.
