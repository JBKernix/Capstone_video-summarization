# Full Pipeline

이 문서는 `scripts/run_pipeline.py`가 전처리, 오디오 추출, 시각 정보 분석, STT 단계를 순서대로 실행하는 전체 흐름을 설명한다. 현재 전체 파이프라인은 요약 단계까지 자동 실행하지 않고, 구현되어 있는 모듈들을 연결해 중간 결과를 생성한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `scripts/run_pipeline.py` | 전체 파이프라인 실행 진입점 |
| `modules/preprocess` | 영상 형식 확인, 영상 정보 추출, 프레임 샘플링, 오디오 추출 |
| `modules/vision` | 프레임 이미지 OCR과 시각 정보 생성 |
| `modules/stt` | Whisper 기반 음성 인식 결과 생성 |
| `configs/stt_config.yaml` | STT 실행 설정 |
| `runs/` | 전체 파이프라인 결과 저장 위치 |

## 전체 실행 흐름

```text
scripts/run_pipeline.py
    -> parse_args()
    -> validate_process_isolation()
    -> ensure_mp4_video()
    -> run_preprocess_step()
        -> get_video_info()
        -> sample_frames()
        -> runs/metadata/frame_metadata.json 생성
    -> run_audio_step()
        -> extract_audio()
        -> runs/audio/audio.wav 생성
    -> run_vision_step()
        -> 별도 프로세스에서 modules.vision 실행
        -> runs/vision/vision_result.json 생성
    -> run_stt_step()
        -> 별도 프로세스에서 modules.stt 실행
        -> runs/stt/stt_result.json 생성
        -> runs/stt/stt_result.txt 생성
```

## 1. 전처리 단계

전처리 단계는 영상 파일을 확인하고 프레임 메타데이터를 생성한다.

```python
metadata_path = run_preprocess_step(
    video_path=video_path,
    run_dir=run_dir,
    method=args.method,
    interval_seconds=args.interval_seconds,
    scene_threshold=args.scene_threshold,
)
```

이 단계의 출력은 다음 파일이다.

```text
runs/metadata/frame_metadata.json
```

프레임 추출 방식은 `interval`과 `scene_change` 중 하나를 사용할 수 있다.

## 2. 오디오 추출 단계

오디오 추출 단계는 영상 파일에서 STT 입력용 WAV 파일을 만든다.

```python
audio_path = run_audio_step(video_path=video_path, run_dir=run_dir)
```

출력 파일은 다음과 같다.

```text
runs/audio/audio.wav
```

기본 설정은 STT에 사용하기 쉬운 16kHz mono WAV다.

## 3. 시각 정보 분석 단계

시각 정보 분석 단계는 프레임 메타데이터를 읽고 PaddleOCR 기반 OCR 결과를 생성한다.

```python
vision_path = run_vision_step(
    metadata_path=metadata_path,
    run_dir=run_dir,
    ocr_lang=args.ocr_lang,
    isolated=not args.vision_same_process,
)
```

출력 파일은 다음과 같다.

```text
runs/vision/vision_result.json
```

기본값에서는 이 단계가 별도 프로세스에서 실행된다.

## 4. STT 단계

STT 단계는 오디오 파일을 Whisper로 음성 인식하고 JSON/TXT 결과를 저장한다.

```python
stt_json_path, stt_text_path = run_stt_step(
    audio_path=audio_path,
    run_dir=run_dir,
    stt_options=stt_options,
    isolated=not args.stt_same_process,
)
```

출력 파일은 다음과 같다.

```text
runs/stt/stt_result.json
runs/stt/stt_result.txt
```

STT 옵션은 `configs/stt_config.yaml`과 명령줄 인자를 합쳐 구성한다.

## 프로세스 분리 구조

Whisper는 PyTorch를 통해 CUDA/cuDNN DLL을 로드하고, PaddleOCR는 PaddlePaddle을 통해 CUDA/cuDNN DLL을 로드한다. 두 프레임워크가 같은 Python 프로세스에 함께 로드되면 cuDNN DLL 충돌이 발생할 수 있다.

이를 피하기 위해 전체 파이프라인은 기본적으로 다음처럼 실행한다.

| 단계 | 기본 실행 방식 |
| --- | --- |
| 전처리 | 부모 프로세스 |
| 오디오 추출 | 부모 프로세스 |
| vision/PaddleOCR | 별도 spawn 프로세스 |
| STT/Whisper/PyTorch | 별도 spawn 프로세스 |

`--vision-same-process`와 `--stt-same-process`를 동시에 사용하면 두 프레임워크가 같은 프로세스에 로드될 수 있으므로 `validate_process_isolation()`에서 실행을 차단한다.

## 주요 명령줄 옵션

| 옵션 | 의미 |
| --- | --- |
| `--video` | 입력 영상 파일 경로 |
| `--run-dir` | 결과 저장 디렉터리 |
| `--method` | 프레임 추출 방식. `interval` 또는 `scene_change` |
| `--interval-seconds` | interval 방식의 프레임 추출 간격 |
| `--scene-threshold` | scene_change 방식의 장면 전환 임계값 |
| `--ocr-lang` | PaddleOCR 언어 코드 |
| `--skip-vision` | vision 단계 생략 |
| `--skip-stt` | STT 단계 생략 |
| `--stt-model-size` | Whisper 모델 크기 |
| `--stt-device` | STT 실행 장치 |
| `--stt-timestamps` | TXT 결과에 segment 시간 포함 |

## 출력 디렉터리 구조

기본 실행 결과는 `runs/` 아래에 생성된다.

```text
runs/
    input/
    metadata/
        frame_metadata.json
    frames/
        frame_000001.jpg
    audio/
        audio.wav
    vision/
        vision_result.json
    stt/
        stt_result.json
        stt_result.txt
```

## 실패 처리

각 단계는 입력 파일이 없거나 외부 도구 실행이 실패하면 예외를 발생시킨다.

vision과 STT는 별도 프로세스에서 실행되므로, 자식 프로세스에서 발생한 예외는 큐를 통해 부모 프로세스로 전달된다. 부모 프로세스는 실패 결과를 받으면 `RuntimeError`를 발생시킨다.

```text
Vision step failed in the isolated process.
STT step failed in the isolated process.
```

자식 프로세스가 결과를 반환하지 못하고 종료되면 exit code를 포함한 오류를 발생시킨다.

## 현재 한계

1. 요약 단계는 아직 전체 파이프라인에 포함되어 있지 않다.
2. vision과 STT는 순차 실행되며 병렬 실행하지 않는다.
3. 별도 프로세스 실행은 DLL 충돌을 줄이지만 모델을 매번 새로 로드하므로 실행 시간이 늘어날 수 있다.
4. 실패한 단계 이후의 복구나 재시도 기능은 아직 없다.
5. 실행 결과 디렉터리를 run ID나 timestamp로 자동 분리하지 않는다.
