# 오디오 추출

`modules/preprocess/audio_extractor.py`는 영상 파일에서 STT 입력으로 사용할 WAV 오디오를 추출합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/audio_extractor.py` | 오디오 추출 함수 |
| `modules/preprocess/ffmpeg_utils.py` | FFmpeg 실행 |
| `scripts/run_pipeline.py` | 전체 파이프라인에서 오디오 추출 호출 |

## 주요 함수

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
| `video_path` | 원본 영상 파일 |
| `audio_path` | 저장할 WAV 파일 |
| `sample_rate` | 출력 sample rate, 기본 `16000` |
| `channels` | 출력 채널 수, 기본 `1` |
| `overwrite` | 기존 파일 덮어쓰기 여부 |

## FFmpeg 명령 구조

개념적으로 다음 명령과 같습니다.

```text
ffmpeg -y -i input.mp4 -vn -acodec pcm_s16le -ar 16000 -ac 1 runs/audio/audio.wav
```

## 출력

기본 출력은 다음 경로입니다.

```text
runs/audio/audio.wav
```

## 예외

| 상황 | 예외 |
| --- | --- |
| 입력 영상 없음 | `FileNotFoundError` |
| FFmpeg 실행 실패 | `subprocess.CalledProcessError` |
| FFmpeg 실행 파일 없음 | `RuntimeError` |

## 주의 사항

- STT 호환성을 위해 기본값은 16kHz mono WAV입니다.
- 오디오 트랙이 없는 영상은 FFmpeg 단계에서 실패할 수 있습니다.
