# FFmpeg Utils

이 문서는 `modules/preprocess/ffmpeg_utils.py`가 ffmpeg와 ffprobe 실행을 공통으로 처리하는 방식을 설명한다. 이 모듈은 전처리 코드가 직접 `subprocess.run()`을 반복해서 사용하지 않도록 명령 실행, 실행 파일 확인, JSON 파싱, 로그 timestamp 추출을 한곳에 모아둔다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/ffmpeg_utils.py` | ffmpeg/ffprobe 실행 공통 유틸 |
| `modules/preprocess/video_info.py` | `run_ffprobe_json()`으로 영상 정보 조회 |
| `modules/preprocess/frame_sampler.py` | `run_ffmpeg()`, `parse_showinfo_timestamps()`, `remove_files()` 사용 |
| `modules/preprocess/audio_extractor.py` | `run_ffmpeg()`으로 오디오 추출 |

## 전체 실행 흐름

```text
전처리 함수
    -> run_ffmpeg() 또는 run_ffprobe_json() 호출
        -> ensure_command()로 실행 파일 위치 확인
        -> run_command()로 subprocess 실행
        -> stdout/stderr 캡처
    -> 필요한 경우 JSON 또는 showinfo 로그 파싱
```

## 1. `ensure_command()`

`ffmpeg`, `ffprobe` 같은 실행 파일이 `PATH`에 등록되어 있는지 확인한다.

```python
resolved = shutil.which(command)
```

실행 파일을 찾으면 실제 경로를 반환하고, 찾지 못하면 `RuntimeError`를 발생시킨다.

```python
ensure_command("ffmpeg")
ensure_command("ffprobe")
```

## 2. `run_command()`

명령어 배열을 받아 실행하고 결과를 `subprocess.CompletedProcess[str]`로 반환한다.

```python
result = run_command(["ffmpeg", "-version"])
```

현재 설정은 다음과 같다.

```python
subprocess.run(
    list(args),
    check=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)
```

| 옵션 | 의미 |
| --- | --- |
| `check=True` | 명령 실패 시 `CalledProcessError` 발생 |
| `text=True` | stdout/stderr를 문자열로 반환 |
| `encoding="utf-8"` | 출력 문자열을 UTF-8로 디코딩 |
| `errors="replace"` | 디코딩 불가능한 문자를 대체 문자로 처리 |
| `stdout=subprocess.PIPE` | 표준 출력을 캡처 |
| `stderr=subprocess.PIPE` | 표준 오류를 캡처 |

명령 인자가 비어 있으면 `ValueError`가 발생한다.

## 3. `run_ffmpeg()`

전달받은 인자 앞에 ffmpeg 실행 파일 경로를 붙여 실행한다.

```python
run_ffmpeg([
    "-y",
    "-i", "data/input/video.mp4",
    "-q:v", "2",
    "runs/frames/frame_%06d.jpg",
])
```

내부 동작은 다음 한 줄로 정리된다.

```python
return run_command([ensure_command("ffmpeg"), *args])
```

## 4. `run_ffprobe_json()`

ffprobe를 JSON 출력 모드로 실행하고 결과를 딕셔너리로 변환한다.

```python
data = run_ffprobe_json([
    "-show_entries",
    "format=duration",
    "data/input/video.mp4",
])
```

내부적으로 다음 옵션을 항상 추가한다.

```text
-v error
-print_format json
```

따라서 호출하는 쪽에서는 조회할 항목만 인자로 넘기면 된다.

## 5. `parse_showinfo_timestamps()`

ffmpeg `showinfo` 로그에서 `pts_time` 값을 찾아 float 리스트로 반환한다. 장면 전환 프레임을 추출할 때 실제 선택된 프레임의 timestamp를 얻기 위해 사용한다.

```python
SHOWINFO_TIME_PATTERN = re.compile(r"pts_time:(?P<time>[0-9]+(?:\.[0-9]+)?)")
```

예를 들어 stderr에 다음 로그가 있다면:

```text
pts_time:12.345
```

결과 리스트에는 `12.345`가 들어간다.

```python
timestamps = parse_showinfo_timestamps(result.stderr)
```

## 6. `remove_files()`

파일 목록을 받아 존재하는 파일만 삭제한다. 프레임을 다시 추출하기 전에 같은 prefix의 기존 이미지 파일을 정리할 때 사용한다.

```python
remove_files(frames_dir.glob("frame_*.jpg"))
```

존재하지 않는 파일은 무시한다.

## 실패 처리

명령 배열이 비어 있으면 `ValueError`가 발생한다.

ffmpeg 또는 ffprobe가 설치되어 있지 않거나 `PATH`에 없으면 `RuntimeError`가 발생한다.

명령 실행 결과가 실패 코드이면 `subprocess.CalledProcessError`가 발생한다. 이 예외에는 실행 인자, stdout, stderr가 포함되므로 상위 호출부에서 원인을 확인할 수 있다.

## 현재 한계

1. 모든 명령은 stdout과 stderr를 메모리에 캡처한다. 출력이 매우 큰 작업에는 적합하지 않을 수 있다.
2. stderr 인코딩이 UTF-8이 아닌 환경에서는 일부 문자가 `errors="replace"`에 의해 대체될 수 있다.
3. 명령 실행 정책만 담당하며, 영상 확장자 허용 여부나 mp4 변환 같은 업무 규칙은 호출부에서 처리해야 한다.