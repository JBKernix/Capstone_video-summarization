# 오디오 추출

`modules/preprocess/audio_extractor.py`는 영상 파일에서 STT 입력으로 사용할 WAV 오디오를 추출합니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/audio_extractor.py` | 오디오 추출 함수 |
| `modules/preprocess/ffmpeg_utils.py` | `run_ffmpeg_with_progress()`로 FFmpeg 실행 |
| `modules/preprocess/video_info.py` | 진행률 계산 기준이 되는 영상 길이 조회 |
| `modules/common/progress.py` | `report_progress()`로 `STEP_AUDIO_EXTRACTION` 진행률 보고 |
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

실제로는 `run_ffmpeg_with_progress()`를 통해 실행되므로 `-nostdin -progress pipe:1 -nostats`가 추가로 붙습니다.

## 진행률 보고

`extract_audio()`는 오디오를 추출하기 전에 `get_video_info(video_path).duration`으로 영상 길이를 구합니다(조회 실패 시 `0.0`으로 처리해 진행률 계산을 생략). 이 길이를 기준으로 `run_ffmpeg_with_progress()`가 호출될 때마다 다음과 같이 `modules.common.progress.report_progress()`를 호출합니다.

```python
report_progress(STEP_AUDIO_EXTRACTION, f"오디오 추출 중 ({percent:.0f}%)", percent)
# 완료 시
report_progress(STEP_AUDIO_EXTRACTION, "오디오 추출 완료", 100.0)
```

파이프라인 UI/로그는 표준 출력의 `##PROGRESS##` 마커 줄을 폴링해 이 진행률을 표시합니다.

## 출력

기본 출력은 다음 경로입니다.

```text
runs/audio/audio.wav
```

## 예외

| 상황 | 예외 |
| --- | --- |
| 입력 영상 없음 | `FileNotFoundError` |
| FFmpeg 실행 실패 | stdout/stderr를 포함한 `RuntimeError` |
| FFmpeg 실행 파일 없음 | `RuntimeError` |

## 주의 사항

- STT 호환성을 위해 기본값은 16kHz mono WAV입니다.
- 오디오 트랙이 없는 영상은 FFmpeg 단계에서 실패할 수 있습니다.
