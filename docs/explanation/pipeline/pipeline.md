# Full Pipeline

## 개요

`scripts/run_pipeline.py`는 영상 전처리, 오디오 추출, 프레임 OCR 분석, STT를 순서대로 실행하는 전체 파이프라인 진입점이다.

현재 자동 실행 범위는 다음과 같다.

```text
입력 영상
  -> MP4 확인/변환
  -> 프레임 추출
  -> 오디오 추출
  -> EasyOCR 기반 프레임 분석
  -> Whisper 기반 STT
  -> runs/ 하위 결과 파일 저장
```

LLM 요약 단계는 폴더와 설정 파일만 준비되어 있고, 아직 전체 파이프라인에는 연결되어 있지 않다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_pipeline.py` | 전체 파이프라인 실행 진입점 |
| `modules/preprocess/` | 영상 정보 확인, MP4 보장, 프레임 추출, 오디오 추출 |
| `modules/vision/` | EasyOCR 기반 프레임 텍스트 추출과 시각 정보 생성 |
| `modules/stt/` | Whisper 기반 음성 인식 결과 생성 |
| `configs/stt_config.yaml` | STT 기본 옵션 |
| `runs/` | 실행 결과 저장 위치 |

## 실행 흐름

```text
main()
  -> parse_args()
  -> validate_process_isolation()
  -> build_stt_options()
  -> ensure_mp4_video()
  -> run_preprocess_step()
      -> get_video_info()
      -> sample_frames()
      -> runs/metadata/frame_metadata.json
  -> run_audio_step()
      -> extract_audio()
      -> runs/audio/audio.wav
  -> run_vision_step()
      -> isolated child process
      -> analyze_frames_metadata()
      -> runs/vision/vision_result.json
  -> run_stt_step()
      -> isolated child process
      -> run_chunked_whisper_stt() 또는 run_whisper_stt()
      -> runs/stt/stt_result.json
      -> runs/stt/stt_result.txt
```

## 주요 단계

### 1. 입력 영상 준비

`ensure_mp4_video()`는 입력 영상이 MP4인지 확인한다. MP4가 아니면 `runs/input/` 아래에 MP4 파일을 생성해 이후 단계가 같은 형식의 영상을 사용하도록 맞춘다.

### 2. 프레임 추출

`run_preprocess_step()`은 영상 정보 확인 후 `sample_frames()`를 호출한다.

지원하는 추출 방식은 두 가지다.

| 방식 | 설명 |
| --- | --- |
| `interval` | 일정 시간 간격으로 프레임 추출 |
| `scene_change` | 장면 전환 기준으로 프레임 추출 |

결과 파일:

```text
runs/frames/frame_000001.jpg
runs/metadata/frame_metadata.json
```

### 3. 오디오 추출

`run_audio_step()`은 영상에서 STT 입력용 WAV 파일을 추출한다.

기본 출력은 16kHz mono WAV다.

```text
runs/audio/audio.wav
```

### 4. 프레임 시각 정보 분석

`run_vision_step()`은 `frame_metadata.json`을 읽고 각 프레임 이미지를 EasyOCR로 분석한다.

기본적으로 별도 `spawn` 자식 프로세스에서 실행된다. 이 구조는 무거운 모델 로딩이 부모 프로세스에 남지 않도록 하기 위한 것이다.

```text
runs/vision/vision_result.json
```

### 5. STT

`run_stt_step()`은 추출된 오디오를 Whisper로 변환한다. 기본 설정은 `configs/stt_config.yaml`에서 읽고, 명령줄 인자가 있으면 명령줄 값이 우선한다.

```text
runs/stt/stt_result.json
runs/stt/stt_result.txt
```

## 주요 옵션

| 옵션 | 설명 |
| --- | --- |
| `--video` | 입력 영상 경로 |
| `--run-dir` | 결과 저장 디렉터리 |
| `--method` | 프레임 추출 방식: `interval`, `scene_change` |
| `--interval-seconds` | interval 방식의 추출 간격 |
| `--scene-threshold` | scene_change 방식의 장면 전환 임계값 |
| `--ocr-lang` | OCR 언어 설정. 기본값은 `korean` |
| `--skip-vision` | 프레임 OCR 분석 생략 |
| `--vision-same-process` | vision 단계를 부모 프로세스에서 실행 |
| `--skip-stt` | STT 생략 |
| `--stt-same-process` | STT 단계를 부모 프로세스에서 실행 |
| `--stt-model-size` | Whisper 모델 크기 |
| `--stt-language` | STT 언어 코드 |
| `--stt-device` | STT 실행 장치: `cpu`, `cuda` |
| `--stt-chunked` | 오디오를 chunk 단위로 STT 처리 |
| `--stt-no-chunked` | chunk 분할 없이 STT 처리 |
| `--stt-timestamps` | TXT 결과에 timestamp 포함 |

## 출력 구조

```text
runs/
  input/
  frames/
    frame_000001.jpg
  metadata/
    frame_metadata.json
  audio/
    audio.wav
  vision/
    vision_result.json
  stt/
    stt_result.json
    stt_result.txt
```

## 실패 처리

vision과 STT는 자식 프로세스에서 실행될 수 있다. 자식 프로세스에서 예외가 발생하면 `_run_isolated_worker()`가 traceback을 받아 부모 프로세스에서 `RuntimeError`로 다시 발생시킨다.

대표 오류:

```text
Vision step failed in the isolated process.
STT step failed in the isolated process.
```

프레임 이미지 경로는 `frame_metadata.json`의 상대경로를 기준으로 복원한다. 현재 구현은 상위 폴더 중 `modules/`와 `scripts/`가 함께 있는 폴더를 프로젝트 루트로 판단한다.

## 현재 제한

1. LLM 요약 단계는 아직 구현되지 않았다.
2. vision과 STT는 순차 실행된다.
3. `runs/`가 실행마다 자동 분리되지 않아 이전 결과를 덮어쓸 수 있다.
4. EasyOCR 첫 실행 시 모델 다운로드가 필요할 수 있다.
