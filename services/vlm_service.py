from pathlib import Path

from models.vlm_loader import VLMLoader, VLMConfig


class VLMService:
    def __init__(self):
        config = VLMConfig(
            device="cuda",
            torch_dtype="float16",
        )
        self.loader = VLMLoader(config)

    def summarize_frame(self, image_path: str, ocr_text: str = "") -> str:
        path = Path(image_path)

        if not path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {path}")

        prompt = f"""
이 이미지는 영상에서 중요 구간으로 판단되어 추출된 프레임입니다.

[OCR 분석 결과]
{ocr_text}

이미지와 OCR 결과를 함께 참고하여 한국어로 요약해줘.

[분석 기준]
1. 화면에 보이는 장면 설명
2. 발표 자료, 표, 차트, 코드, 문서 여부
3. OCR 텍스트와 이미지 내용의 관계
4. 영상 요약에 반영할 핵심 시각 정보
5. 불확실한 내용은 단정하지 않기

[출력 형식]
## 프레임 시각 요약

### 장면 설명
-

### 화면 텍스트 기반 정보
-

### 요약에 반영할 핵심 정보
-
"""

        return self.loader.describe_image(
            image=path,
            prompt=prompt,
            max_new_tokens=512,
        )