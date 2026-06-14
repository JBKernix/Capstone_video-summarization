# LLM Summary

## 개요

`modules/llm`은 STT 결과와 vision 결과를 결합해 최종 영상 요약을 생성하기 위한 영역이다.

현재 이 단계는 아직 구현되지 않았다. 파일과 설정 위치만 준비되어 있으며, `scripts/run_pipeline.py`의 전체 실행 흐름에도 연결되어 있지 않다.

## 관련 파일

| 파일 | 상태 | 역할 |
| --- | --- | --- |
| `modules/llm/prompt_builder.py` | 비어 있음 | STT/vision 결과를 LLM 프롬프트로 변환 예정 |
| `modules/llm/summarizer.py` | 비어 있음 | LLM 호출 및 요약 결과 생성 예정 |
| `modules/llm/__init__.py` | 비어 있음 | LLM 모듈 export 예정 |
| `scripts/run_summary.py` | 비어 있음 | 요약 단계 단독 실행 스크립트 예정 |
| `configs/llm_config.yaml` | 비어 있음 | LLM 모델과 요약 옵션 설정 예정 |

## 목표 실행 흐름

구현이 완료되면 예상 흐름은 다음과 같다.

```text
run_summary.py 또는 run_pipeline.py
  -> stt_result.json 로드
  -> ocr_result.json 로드
  -> prompt_builder에서 통합 프롬프트 생성
  -> summarizer에서 LLM 호출
  -> summary_result.json 또는 summary_result.md 저장
```

## 예상 입력

STT 결과:

```text
runs/stt/stt_result.json
```

vision 결과:

```text
runs/ocr/ocr_result.json
```

## 예상 출력

향후 요약 결과는 다음 위치 중 하나로 저장하는 것이 자연스럽다.

```text
runs/summary/summary_result.json
runs/summary/summary_result.md
```

## `prompt_builder.py` 설계 방향

`prompt_builder.py`는 STT와 vision 결과를 LLM이 읽기 쉬운 구조로 바꾸는 역할을 맡는 것이 적절하다.

포함할 정보:

| 정보 | 설명 |
| --- | --- |
| 전체 STT 텍스트 | 영상의 음성 내용 |
| STT segments | 시간대별 발화 내용 |
| 중요 프레임 | `importance_score`가 높은 프레임 |
| OCR 텍스트 | 화면에 등장한 주요 텍스트 |
| timestamp | 음성과 화면 정보를 연결하기 위한 시간 정보 |

## `summarizer.py` 설계 방향

`summarizer.py`는 실제 LLM 호출을 담당한다.

예상 책임:

1. LLM 설정 로드
2. prompt 생성 함수 호출
3. 모델 API 호출
4. 요약 결과 정규화
5. 결과 파일 저장

## 현재 제한

1. 요약 코드는 아직 없다.
2. API key, 모델명, 프롬프트 템플릿 설정도 없다.
3. 전체 파이프라인은 STT 결과 생성까지만 자동 수행한다.
4. README의 “LLM 요약” 설명은 목표 구조에 가깝고 현재 구현 상태와 차이가 있다.
