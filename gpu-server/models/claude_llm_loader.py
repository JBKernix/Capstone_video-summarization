from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from typing import Optional

import anthropic

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_PROMPT = "당신은 영상 내용을 정확하고 간결하게 요약하는 AI입니다."


@dataclass
class ClaudeLLMConfig:
    model: str = "claude-haiku-4-5"
    api_key: Optional[str] = None
    system_prompt: str = DEFAULT_SYSTEM_PROMPT


class ClaudeLLMLoader:
    """
    Anthropic API(Claude) 기반 LLM 로더.

    LLMLoader와 동일한 load/unload/generate 인터페이스를 제공해
    LLMService/FinalService가 로컬 모델과 API 모델을 구분 없이 사용할 수 있게 합니다.
    """

    def __init__(self, config: Optional[ClaudeLLMConfig] = None):
        self.config = config or ClaudeLLMConfig()
        self.client: Optional[anthropic.Anthropic] = None

    def load(self):
        if self.client is None:
            api_key = self.config.api_key or os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "ANTHROPIC_API_KEY가 설정되어 있지 않습니다. "
                    "환경변수로 Anthropic API 키를 설정해주세요."
                )
            self.client = anthropic.Anthropic(api_key=api_key)

        return self.client, None

    def unload(self) -> None:
        # API 기반 백엔드는 해제할 GPU 자원이 없습니다.
        self.client = None

    def generate(self, prompt: str, max_new_tokens: int) -> str:
        client, _ = self.load()

        logger.info(
            "Claude LLM generate start | model=%s | max_tokens=%d",
            self.config.model,
            max_new_tokens,
        )
        started_at = time.perf_counter()
        try:
            response = client.messages.create(
                model=self.config.model,
                max_tokens=max_new_tokens,
                system=self.config.system_prompt,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.RateLimitError as error:
            raise ValueError(
                "Claude API 요청 한도를 초과했습니다. 잠시 후 다시 시도해주세요."
            ) from error
        except anthropic.AuthenticationError as error:
            raise ValueError(
                "Claude API 인증에 실패했습니다. API 키를 확인해주세요."
            ) from error
        except anthropic.APIStatusError as error:
            raise ValueError(
                f"Claude API 오류가 발생했습니다 (status={error.status_code})."
            ) from error
        except anthropic.APIConnectionError as error:
            raise ValueError(
                "Claude API 연결에 실패했습니다. 네트워크 상태를 확인해주세요."
            ) from error
        finally:
            logger.info(
                "Claude LLM generate end | model=%s | max_tokens=%d | "
                "elapsed_seconds=%.3f",
                self.config.model,
                max_new_tokens,
                time.perf_counter() - started_at,
            )

        if response.stop_reason == "refusal":
            raise ValueError("Claude가 안전상의 이유로 응답 생성을 거부했습니다.")

        text = "".join(
            block.text for block in response.content if block.type == "text"
        )
        return text.strip()
