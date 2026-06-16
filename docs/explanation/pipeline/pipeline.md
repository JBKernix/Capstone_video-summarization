# Full Pipeline

## 개요

`scripts/run_pipeline.py`는 입력 영상에서 오디오를 추출하고, STT와 LLM 요약으로 중요 구간을 찾은 뒤 해당 구간의 프레임을 분석하는 전체 파이프라인 진입점이다.

## 실행 흐름

```text
입력 영상
  -> MP4 확인/변환
  -> 오디오 추출
  -> Whisper STT
  -> LLM STT 요약 및 important_segments 생성
  -> 중요 구간 interval 또는 화면 전환 프레임 추출
  -> EasyOCR 기반 OCR 분석
```

```text
main()
  -> ensure_mp4_video()
  -> run_audio_step()
  -> run_stt_step()
  -> run_llm_summary_step()
  -> run_preprocess_step()
      -> sample_frames()
      -> runs/metadata/frame_metadata.json
  -> run_ocr_step()
      -> runs/ocr/ocr_result.json
```

## 주요 단계

### 1. 입력 영상 준비

`ensure_mp4_video()`는 입력 영상이 MP4인지 확인한다. MP4가 아니면 `runs/data/input/` 아래에 변환된 MP4 파일을 생성한다.

### 2. 오디오 추출

`run_audio_step()`은 STT 입력용 WAV 파일을 생성한다.

```text
runs/audio/audio.wav
```

### 3. STT 및 요약

`run_stt_step()`은 Whisper로 음성을 텍스트와 timestamp 구간으로 변환한다. 이후 `run_llm_summary_step()`이 STT 결과를 요약하고 `important_segments`를 생성한다.

```text
runs/stt/stt_result.json
runs/stt/stt_result.txt
runs/llm/stt_summary.txt
runs/llm/stt_summary_result.json
```

### 4. 중요 구간 프레임 추출

`run_preprocess_step()`은 LLM 요약 JSON의 `important_segments`를 읽고, 각 구간 안에서 interval 또는 화면 전환 방식으로 프레임을 추출한다. `--method`로 두 결과를 비교할 수 있다.

```text
runs/frames/frame_000001.jpg
runs/metadata/frame_metadata.json
```

중요 구간이 없으면 전체 영상을 대신 추출하지 않고 빈 metadata를 생성한다.

### 5. OCR 분석

`run_ocr_step()`은 `frame_metadata.json`에 포함된 이미지에 EasyOCR을 실행한다.

```text
runs/ocr/ocr_result.json
```

## 주요 옵션

| 옵션 | 설명 |
| --- | --- |
| `--video` | 입력 영상 경로 |
| `--run-dir` | 결과 저장 디렉터리 |
| `--method` | `interval` 또는 `scene_change`. 기본값은 `interval` |
| `--interval-seconds` | interval 추출 간격. 기본값은 `10.0`초 |
| `--scene-threshold` | 화면 전환 임계값. 기본값은 `0.7` |
| `--scene-min-gap-seconds` | 화면 전환 프레임 최소 간격. 기본값은 `1.0`초 |
| `--ocr-lang` | OCR 언어 설정 |
| `--skip-ocr` | 프레임 OCR 분석 생략 |
| `--skip-stt` | STT 생략. 이후 요약, 프레임 추출, vision도 실행되지 않음 |
| `--stt-model-size` | Whisper 모델 크기 |
| `--stt-language` | STT 언어 코드 |
| `--stt-device` | STT 실행 장치: `cpu`, `cuda` |
| `--stt-timestamps` | TXT 결과에 timestamp 포함 |

## 출력 구조

```text
runs/
  data/input/
  audio/
    audio.wav
  stt/
    stt_result.json
    stt_result.txt
  llm/
    stt_summary.txt
    stt_summary_result.json
  frames/
    frame_000001.jpg
  metadata/
    frame_metadata.json
  ocr/
    ocr_result.json
```

## 실패 처리

STT 또는 OCR 단계에서 예외가 발생하면 파이프라인을 중단한다. 입력 영상, STT 결과, LLM 요약 결과가 없으면 해당 결과에 의존하는 뒤 단계는 건너뛴다.

같은 `run_dir`을 반복 사용하면 이전 결과를 덮어쓸 수 있다.
