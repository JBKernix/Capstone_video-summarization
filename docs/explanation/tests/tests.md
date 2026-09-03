# 테스트

`tests/` 폴더는 주요 모듈과 앱 보조 로직을 검증하는 테스트를 담고 있습니다.

## 테스트 파일

| 파일 | 대상 |
| --- | --- |
| `tests/test_audio_extractor.py` | 오디오 추출 |
| `tests/test_frame_sampler.py` | 프레임 샘플링 |
| `tests/test_pipeline.py` | 파이프라인 보조 흐름 |
| `tests/test_stt.py` | STT 포맷팅/실행 관련 동작 |
| `tests/test_vlm_summary.py` | VLM 요약 클라이언트 |
| `tests/test_summary_result.py` | 앱 최종 요약 로더와 영상 경로 해석 |

## 실행

```bash
pytest
```

특정 파일만 실행:

```bash
pytest tests/test_summary_result.py
```

`python -m unittest discover`로도 실행할 수는 있지만, `tests/test_frame_sampler.py`와 `tests/test_vlm_summary.py`는 `unittest.TestCase`가 아닌 pytest 스타일 함수(`tmp_path`/`monkeypatch` fixture 사용)로 작성되어 있어 `unittest discover`는 이 파일들을 수집조차 하지 못하고 조용히 건너뜁니다. 그 결과 실제보다 적은 테스트 수가 통과한 것으로 보일 수 있으므로, 전체 테스트는 반드시 `pytest`로 실행해야 합니다.

## 오디오/프레임 샘플링 테스트: `run_ffmpeg_with_progress` 모킹

`extract_audio()`(오디오 추출)와 `sample_scene_change_frames()`(장면 전환 프레임 샘플링)가 기존 `run_ffmpeg()` 대신 스트리밍 진행률 콜백을 받는 `run_ffmpeg_with_progress()`를 호출하도록 바뀌면서, 관련 테스트도 함께 갱신되었습니다.

- `tests/test_audio_extractor.py::test_extract_audio_builds_ffmpeg_command`는 `audio_extractor.get_video_info`(영상 길이 조회)와 `audio_extractor.run_ffmpeg_with_progress`를 모킹하고, 호출 인자로 전달된 FFmpeg 명령어 리스트와 총 길이(`args[1]`)를 검증합니다.
- `tests/test_frame_sampler.py::test_scene_change_sampling_uses_important_ranges_and_showinfo_timestamps`도 동일하게 `frame_sampler.run_ffmpeg_with_progress`와 `frame_sampler.get_video_info`를 모킹합니다.
- `run_ffmpeg`를 직접 모킹해 "호출되면 안 된다"를 검증하던 기존 테스트(`test_empty_time_ranges_write_empty_metadata_without_running_ffmpeg`, `test_empty_scene_change_ranges_do_not_run_ffmpeg`)는 그대로 유지됩니다. 이 경로들은 중요 구간이 비어 있어 FFmpeg 실행 자체가 스킵되는 경우이므로 `run_ffmpeg_with_progress`로의 전환과 무관합니다.

## 앱 결과 로더 테스트

`test_summary_result.py`는 다음 동작을 확인합니다.

- `final_summary_result.json`이 있으면 TXT보다 우선 사용
- JSON이 없으면 `final_summary.txt`로 fallback
- 결과 파일이 없으면 `FileNotFoundError`
- `summary`, `final_summary` 키에서 Markdown 요약 추출
- 구조화 요약 필드 감지
- 명시된 영상 경로가 존재하면 그 경로를 사용

## 알려진 실패 테스트

`tests/test_pipeline.py::PipelineVlmTests::test_main_requests_vlm_summary_after_ocr`는 `run_pipeline.main()`의 STT~VLM 단계만 모킹하고 `run_final_summary_step`은 모킹하지 않습니다. STT 요약/VLM 요약 결과가 모두 채워지면 `main()`이 7단계(최종 통합 요약)까지 진행해 `run_final_summary_step`을 실제로 호출하는데, 이때 전달되는 경로들이 임시 디렉터리에 실존하지 않아 실패합니다. 이 세션의 변경과는 무관하게 이전부터 실패하던 테스트입니다.

## 주의 사항

- 일부 테스트는 FFmpeg/FFprobe 실행 가능 여부에 영향을 받을 수 있습니다.
- Whisper, EasyOCR, GPU 서버를 직접 사용하는 테스트는 환경에 따라 느리거나 실패할 수 있습니다.
- `.pytest_cache/`는 로컬 캐시이며 문서나 소스 코드 대상이 아닙니다.

## 테스트 작성 기준

새 기능을 추가할 때는 다음 중 하나 이상을 검증하는 테스트를 추가합니다.

- 입력 파일이 없을 때의 예외
- 출력 JSON 구조
- 기본 경로와 옵션 처리
- 외부 서버 응답 형식 처리
- 앱 결과 표시용 fallback 처리
- 일부 실패가 전체 결과에 미치는 영향
