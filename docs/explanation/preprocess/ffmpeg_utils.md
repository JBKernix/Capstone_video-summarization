# FFmpeg 유틸리티

`modules/preprocess/ffmpeg_utils.py`는 FFmpeg와 FFprobe 실행을 공통으로 감싸는 모듈입니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/ffmpeg_utils.py` | 명령 실행, 진행률 스트리밍, MP4 변환, showinfo 파싱 |
| `modules/preprocess/video_info.py` | FFprobe JSON 사용 |
| `modules/preprocess/audio_extractor.py` | `run_ffmpeg_with_progress()`로 오디오 추출 |
| `modules/preprocess/frame_sampler.py` | `run_ffmpeg_with_progress()`/`run_ffmpeg()`로 프레임 추출 |
| `modules/preprocess/youtube_downloader.py` | yt-dlp로 유튜브 영상 다운로드 |
| `modules/common/progress.py` | `report_progress()` 진행률 마커 출력 |

## 주요 함수

| 함수 | 설명 |
| --- | --- |
| `ensure_command(command)` | 실행 파일이 PATH에 있는지 확인 |
| `run_command(args)` | 명령을 실행하고 실패 시 stdout/stderr를 포함한 `RuntimeError` 발생 |
| `run_ffmpeg(args)` | `ffmpeg` 명령을 블로킹으로 실행, 기본적으로 `-nostdin` 추가 |
| `run_ffmpeg_with_progress(args, total_duration_sec, on_progress)` | `ffmpeg`를 `-progress pipe:1`로 실행하며 진행률(%)을 실시간 콜백으로 전달 |
| `run_ffprobe_json(args)` | `ffprobe`를 JSON 출력 모드로 실행 |
| `ensure_mp4_video(video_path, output_dir)` | MP4가 아니면 H.264/AAC MP4로 변환 |
| `parse_showinfo_timestamps(stderr)` | FFmpeg `showinfo` 로그에서 `pts_time` 추출 |
| `remove_files(files)` | 기존 프레임 파일 정리 |

## 진행률 스트리밍 (`run_ffmpeg_with_progress`)

```python
run_ffmpeg_with_progress(
    args,               # ffmpeg 뒤에 붙일 인자 목록
    total_duration_sec, # 진행률 계산 기준 전체 길이(초), 0 이하이면 진행률 계산 안 함
    on_progress,        # percent(float, 0~100)를 받는 콜백
)
```

`run_ffmpeg()`는 `subprocess.run()`으로 완료까지 기다렸다가 결과를 한 번에 받지만, 이 함수는 `subprocess.Popen()`과 ffmpeg의 `-progress pipe:1 -nostats` 옵션을 사용해 표준 출력을 한 줄씩 읽으면서 진행 상황을 스트리밍합니다.

```text
ffmpeg -nostdin -progress pipe:1 -nostats <args...>
```

내부 동작:

- `out_time=HH:MM:SS.ffffff` 형식의 줄을 `_parse_ffmpeg_time()`으로 초 단위로 변환한 뒤 `seconds / total_duration_sec * 100`으로 퍼센트를 계산해 `on_progress()`를 호출합니다.
- `progress=end` 줄을 만나면 `on_progress(100.0)`을 호출합니다.
- `out_time_ms` 필드는 사용하지 않습니다. ffmpeg 버전에 따라 이 값이 실제로는 마이크로초 단위인 경우가 있어 혼란스럽기 때문에, 대신 시간 문자열(`out_time`)을 직접 파싱하는 방식을 씁니다.
- 인자 목록에 `-nostdin`을 전달해도 중복 추가되지 않도록 걸러낸 뒤 항상 맨 앞에 다시 붙입니다.

반환값은 `run_ffmpeg()`와 동일하게 `subprocess.CompletedProcess`이지만 `stdout`은 항상 비어 있고(진행률 파싱에 소비됨) `stderr`에 ffmpeg 로그 전체가 담깁니다.

실제 사용처:

| 호출 위치 | 용도 |
| --- | --- |
| `audio_extractor.extract_audio()` | 오디오 추출 진행률을 `STEP_AUDIO_EXTRACTION`으로 보고 |
| `frame_sampler.sample_interval_frames()` (구간 미지정) | 전체 영상 fps 필터 추출 진행률을 `STEP_FRAME_EXTRACTION`으로 보고 |
| `frame_sampler.sample_scene_change_frames()` | 장면 전환 탐색 진행률을 `STEP_FRAME_EXTRACTION`으로 보고 |

반면 `frame_sampler._sample_interval_frames_in_ranges()`(중요 구간이 지정된 경우, 타임스탬프마다 개별 ffmpeg 호출)는 여전히 블로킹 방식인 `run_ffmpeg()`를 그대로 사용하고, 매 프레임 처리 후 `report_progress()`를 `"N/M"` 형태의 메시지로 직접 호출합니다. 자세한 내용은 `frame_sampling.md`를 참고하세요.

## MP4 변환

입력 영상 확장자가 `.mp4`이면 원본 경로를 그대로 반환합니다. MP4가 아니면 다음 방식으로 변환합니다.

```text
ffmpeg -y -i input.mov -c:v libx264 -c:a aac -movflags +faststart output.mp4
```

## 유튜브 영상 다운로드 (`youtube_downloader.py`)

`modules/preprocess/youtube_downloader.py`는 FFmpeg 유틸리티는 아니지만 전처리 입력을 준비한다는 점에서 관련 파일로 분류됩니다. 별도 문서가 없어 이 문서에 함께 정리합니다.

```python
is_youtube_url(url) -> bool
download_youtube_video(url, output_path) -> tuple[Path, str]
```

| 함수 | 설명 |
| --- | --- |
| `is_youtube_url(url)` | `youtube.com/watch?v=`, `youtube.com/shorts/`, `youtube.com/embed/`, `youtu.be/` 형식인지 정규식으로 확인 |
| `download_youtube_video(url, output_path)` | yt-dlp로 영상을 다운로드해 `output_path`(확장자는 항상 `.mp4`로 강제)에 저장하고 `(저장 경로, 영상 제목)` 튜플을 반환 |

내부 동작:

- yt-dlp의 `format` 옵션은 `bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best`이며 `merge_output_format: mp4`로 병합합니다.
- **덮어쓰기 버그 방지**: yt-dlp는 기본적으로 대상 파일이 이미 있으면 재다운로드를 건너뜁니다. 같은 `output_path`로 다른 영상을 다시 받으면 이전 영상이 그대로 남는 문제가 있어, 다운로드 전에 기존 출력 파일이 있으면 먼저 삭제하고 `overwrites: True` 옵션도 함께 사용합니다.
- `noplaylist: True`로 재생목록 URL이 와도 첫 영상만 받습니다.
- 반환되는 제목은 yt-dlp가 추출한 메타데이터의 `title` 필드입니다(없으면 빈 문자열).

예외:

| 상황 | 예외 |
| --- | --- |
| 유튜브 링크 형식이 아님 | `ValueError` |
| yt-dlp 미설치 | `ImportError` |
| 다운로드 실패 | `RuntimeError` |
| 다운로드 후 파일을 찾을 수 없음 | `RuntimeError` |

## 예외

| 상황 | 예외 |
| --- | --- |
| 실행 파일을 찾지 못함 | `RuntimeError` |
| 빈 명령 인자 | `ValueError` |
| 명령 실패 | stdout/stderr를 포함한 `RuntimeError` |
| MP4 변환 입력 파일 없음 | `FileNotFoundError` |

## 주의 사항

- 명령은 문자열 조합이 아니라 인자 리스트로 실행합니다.
- `run_ffmpeg()`는 대화형 입력 대기로 멈추지 않도록 `-nostdin`을 자동 추가합니다.
- `run_ffmpeg_with_progress()`도 동일하게 `-nostdin`을 강제하며, 추가로 `-progress pipe:1 -nostats`를 붙여 표준 출력으로 진행률을 스트리밍합니다.
- `run_command()`는 `encoding="utf-8"`, `errors="replace"`를 사용해 Windows 콘솔 출력 문제를 줄입니다.
- `parse_showinfo_timestamps()`는 장면 전환 프레임 수와 timestamp 수를 맞추는 데 사용됩니다.
