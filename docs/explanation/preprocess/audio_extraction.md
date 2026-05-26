# Audio Extraction Pipeline

이 문서는 `modules/preprocess/audio_extractor.py`가 영상 파일에서 오디오 트랙을 추출하는 흐름을 설명한다. 추출된 오디오는 이후 STT 파이프라인에서 음성 인식 입력으로 사용할 수 있도록 WAV 형식, 16kHz, mono 채널을 기본값으로 생성한다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/audio_extractor.py` | 영상에서 오디오 트랙을 추출하고 지정한 경로에 저장 |
| `modules/preprocess/ffmpeg_utils.py` | ffmpeg 실행 공통 유틸 제공 |
| `runs/audio/` | 추출된 오디오 파일을 저장할 수 있는 위치 |

## 전체 실행 흐름

```text
extract_audio()
    -> 입력 영상 경로와 출력 오디오 경로를 Path 객체로 변환
    -> 입력 영상 파일 존재 여부 확인
    -> 출력 디렉터리 생성
    -> ffmpeg 인자 구성
        -> overwrite=True이면 -y 추가
        -> -vn으로 비디오 스트림 제외
        -> pcm_s16le 코덱으로 WAV 오디오 생성
        -> sample_rate가 있으면 -ar 적용
        -> channels가 있으면 -ac 적용
    -> run_ffmpeg()로 명령 실행
    -> 생성된 오디오 경로 반환
```

## 1. `audio_extractor.py`

`audio_extractor.py`는 영상 파일에서 오디오만 분리하는 모듈이다. 내부적으로 직접 `subprocess`를 호출하지 않고 `ffmpeg_utils.py`의 `run_ffmpeg()`를 사용한다.

### `extract_audio()`

```python
extract_audio(
    video_path="data/input/video.mp4",
    audio_path="runs/audio/audio.wav",
    sample_rate=16000,
    channels=1,
    overwrite=True,
)
```

| 인자 | 의미 |
| --- | --- |
| `video_path` | 오디오를 추출할 원본 영상 경로 |
| `audio_path` | 추출된 오디오를 저장할 파일 경로 |
| `sample_rate` | 출력 오디오 샘플레이트. 기본값은 `16000` |
| `channels` | 출력 오디오 채널 수. 기본값은 `1` |
| `overwrite` | 출력 파일이 이미 있을 때 덮어쓸지 여부 |

기본 ffmpeg 인자는 다음과 같이 구성된다.

```python
args.extend(["-i", str(video_path), "-vn", "-acodec", "pcm_s16le"])
```

`-vn`은 비디오 스트림을 제외하고 오디오만 처리하겠다는 의미다. `pcm_s16le`는 WAV 파일에서 흔히 사용하는 비압축 PCM 오디오 코덱이다.

`sample_rate`와 `channels`가 `None`이 아니면 각각 다음 인자가 추가된다.

```python
args.extend(["-ar", str(sample_rate)])
args.extend(["-ac", str(channels)])
```

기본 설정에서는 STT에 사용하기 쉬운 16kHz mono WAV가 만들어진다.

## 입력 파일 형식

입력은 ffmpeg가 읽을 수 있는 영상 파일이면 된다.

```text
data/input/video.mp4
data/input/video.mov
data/input/video.mkv
```

단, 현재 함수는 확장자 검사를 직접 하지 않는다. 실제 지원 여부는 설치된 ffmpeg와 영상의 코덱 지원 상태에 따라 결정된다.

## 출력 파일 형식

출력 경로는 호출하는 쪽에서 정한다. 예시는 다음과 같다.

```text
runs/audio/audio.wav
```

출력 디렉터리는 함수 내부에서 자동으로 생성된다.

```python
audio_path.parent.mkdir(parents=True, exist_ok=True)
```

## 실패 처리

입력 영상이 존재하지 않으면 `FileNotFoundError`가 발생한다.

ffmpeg 실행이 실패하면 `subprocess.CalledProcessError`가 발생한다. 이 경우 입력 파일 경로, 오디오 스트림 존재 여부, ffmpeg 설치 상태, 코덱 지원 여부를 확인해야 한다.

## 현재 한계

1. 입력 영상에 오디오 스트림이 없는 경우 별도 메시지를 만들지 않고 ffmpeg 실패로 처리된다.
2. 출력 확장자와 코덱 조합이 맞지 않아도 사전 검증하지 않는다.
3. STT용 기본값은 16kHz mono로 고정되어 있으므로 다른 모델을 사용할 경우 호출부에서 값을 바꿔야 한다.