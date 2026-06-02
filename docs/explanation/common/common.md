# Common Utilities

이 문서는 `modules/common` 모듈의 공통 유틸리티 역할을 설명한다. 현재 구현된 공통 유틸은 JSON 파일 입출력 중심이며, 일부 파일은 향후 설정, 파일 처리, 시간 처리 기능을 확장하기 위한 자리로 남아 있다.

## 관련 파일

| 파일 | 역할 |
| --- | --- |
| `modules/common/json_utils.py` | JSON 파일 로드/저장 유틸 |
| `modules/common/config.py` | 현재 구현 없음 |
| `modules/common/file_utils.py` | 현재 구현 없음 |
| `modules/common/time_utils.py` | 현재 구현 없음 |

## 전체 구조

```text
modules/common
    -> json_utils.py
        -> load_json()
        -> save_json()
    -> config.py
    -> file_utils.py
    -> time_utils.py
```

현재 실제 동작은 `json_utils.py`에 집중되어 있다.

## 1. `json_utils.py`

`json_utils.py`는 프로젝트 여러 단계에서 사용할 수 있는 JSON 파일 입출력 함수를 제공한다.

### `load_json()`

JSON 파일을 읽어 딕셔너리로 반환한다.

```python
data = load_json("runs/stt/stt_result.json")
```

내부에서는 다음처럼 `utf-8-sig` 인코딩을 사용한다.

```python
with json_path.open("r", encoding="utf-8-sig") as f:
    return json.load(f)
```

`utf-8-sig`를 사용하는 이유는 Windows 환경에서 UTF-8 BOM이 붙은 JSON 파일도 정상적으로 읽기 위해서다. 이 방식은 `vision_formatter.py`에서 프레임 메타데이터를 읽는 방식과 같은 목적을 가진다.

### `save_json()`

딕셔너리 데이터를 JSON 파일로 저장한다.

```python
save_json(data, "runs/output/result.json")
```

저장 전에 부모 디렉터리를 자동으로 생성한다.

```python
json_path.parent.mkdir(parents=True, exist_ok=True)
```

저장 시에는 한글이 깨지지 않도록 `ensure_ascii=False`를 사용하고, 사람이 읽기 쉽도록 `indent=2`를 적용한다.

```python
json.dump(data, f, ensure_ascii=False, indent=2)
```

## 입력 파일 형식

`load_json()`은 표준 JSON 파일을 입력으로 받는다.

```json
{
  "key": "value"
}
```

현재 타입 힌트는 `Dict[str, Any]`이므로 최상위 구조가 딕셔너리인 JSON을 기본 대상으로 한다.

## 출력 파일 형식

`save_json()`은 딕셔너리를 JSON 파일로 저장한다.

```json
{
  "language": "ko",
  "segment_count": 3
}
```

프로젝트의 다른 모듈과 마찬가지로 UTF-8 인코딩, 한글 유지, 2칸 들여쓰기를 사용한다.

## 실패 처리

`load_json()`은 별도 예외 래핑을 하지 않는다. 따라서 다음 예외가 그대로 호출부로 전달된다.

| 상황 | 예외 |
| --- | --- |
| 파일이 없음 | `FileNotFoundError` |
| JSON 형식이 올바르지 않음 | `json.JSONDecodeError` |

`save_json()`은 부모 디렉터리를 자동 생성하지만, 권한 문제나 직렬화할 수 없는 값이 들어오면 표준 Python 예외가 발생한다.

## 현재 한계

1. `load_json()`의 반환 타입이 딕셔너리로 고정되어 있어 JSON 배열을 읽는 용도와는 맞지 않는다.
2. JSON schema 검증은 수행하지 않는다.
3. `config.py`, `file_utils.py`, `time_utils.py`는 아직 구현되지 않았다.
4. 일부 모듈은 아직 자체적으로 `json.load()`와 `json.dump()`를 사용하므로, 향후 공통 유틸로 통일할 수 있다.
