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

## 앱 결과 로더 테스트

`test_summary_result.py`는 다음 동작을 확인합니다.

- `final_summary_result.json`이 있으면 TXT보다 우선 사용
- JSON이 없으면 `final_summary.txt`로 fallback
- 결과 파일이 없으면 `FileNotFoundError`
- `summary`, `final_summary` 키에서 Markdown 요약 추출
- 구조화 요약 필드 감지
- 명시된 영상 경로가 존재하면 그 경로를 사용

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
