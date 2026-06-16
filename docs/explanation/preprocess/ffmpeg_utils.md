# FFmpeg 유틸리티

`modules/preprocess/ffmpeg_utils.py`는 FFmpeg와 FFprobe 실행을 공통으로 감싸는 모듈입니다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/preprocess/ffmpeg_utils.py` | 명령 실행, MP4 변환, showinfo 파싱 |
| `modules/preprocess/video_info.py` | FFprobe JSON 사용 |
| `modules/preprocess/audio_extractor.py` | FFmpeg로 오디오 추출 |
| `modules/preprocess/frame_sampler.py` | FFmpeg로 프레임 추출 |

## 주요 함수

| 함수 | 설명 |
| --- | --- |
| `ensure_command(command)` | 실행 파일이 PATH에 있는지 확인 |
| `run_command(args)` | 명령을 실행하고 실패 시 stdout/stderr를 포함한 `RuntimeError` 발생 |
| `run_ffmpeg(args)` | `ffmpeg` 명령 실행, 기본적으로 `-nostdin` 추가 |
| `run_ffprobe_json(args)` | `ffprobe`를 JSON 출력 모드로 실행 |
| `ensure_mp4_video(video_path, output_dir)` | MP4가 아니면 H.264/AAC MP4로 변환 |
| `parse_showinfo_timestamps(stderr)` | FFmpeg `showinfo` 로그에서 `pts_time` 추출 |
| `remove_files(files)` | 기존 프레임 파일 정리 |

## MP4 변환

입력 영상 확장자가 `.mp4`이면 원본 경로를 그대로 반환합니다. MP4가 아니면 다음 방식으로 변환합니다.

```text
ffmpeg -y -i input.mov -c:v libx264 -c:a aac -movflags +faststart output.mp4
```

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
- `run_command()`는 `encoding="utf-8"`, `errors="replace"`를 사용해 Windows 콘솔 출력 문제를 줄입니다.
- `parse_showinfo_timestamps()`는 장면 전환 프레임 수와 timestamp 수를 맞추는 데 사용됩니다.
