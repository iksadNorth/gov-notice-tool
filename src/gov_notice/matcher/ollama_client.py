import json
import logging
from dataclasses import dataclass

import ollama

from gov_notice.config import settings
from gov_notice.matcher.mcp_server import query_profile
from gov_notice.matcher.prompt import (
    QUERY_PROFILE_TOOL,
    RESPONSE_SCHEMA,
    SYSTEM_PROMPT,
    build_user_prompt,
)

logger = logging.getLogger(__name__)

_client = ollama.Client(host=settings.ollama_host)

MAX_TOOL_CALLS = 4


@dataclass
class JudgeResult:
    is_eligible: bool
    confidence: float
    reason: str
    missing_info: list[str]
    trace: list[dict]


def _to_dict(message) -> dict:
    """ollama 응답 Message 객체/plain dict 둘 다 JSON 직렬화 가능한 dict로 변환."""
    if hasattr(message, "model_dump"):
        return message.model_dump(exclude_none=True)
    return dict(message)


def judge(title: str, content_text: str, profile_label: str) -> JudgeResult:
    """LLM이 query_profile 툴을 능동 호출하며 공고 자격 요건을 판단한다.

    프로필 전체를 프롬프트에 안 넣음 — 필요한 키만 LLM이 그때그때 조회
    (docs/04-llm-matching.md "프로필 능동 쿼리 인터페이스" 참고).
    """
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(title, content_text)},
    ]

    for _ in range(MAX_TOOL_CALLS):
        resp = _client.chat(
            model=settings.ollama_model,
            messages=messages,
            tools=[QUERY_PROFILE_TOOL],
            options={"temperature": 0},
        )
        message = resp["message"]
        messages.append(message)

        tool_calls = message.get("tool_calls")
        if not tool_calls:
            break

        for call in tool_calls:
            args = call["function"]["arguments"]
            result = query_profile(query=args["query"], profile_label=profile_label)
            logger.info("tool_call query_profile(%s) -> %s", args["query"], result)
            messages.append(
                {"role": "tool", "content": json.dumps(result, ensure_ascii=False)}
            )
    else:
        logger.warning("judge: MAX_TOOL_CALLS(%d) 도달, 강제 종료", MAX_TOOL_CALLS)

    # 최종 판단을 구조화 JSON으로 강제 (tools와 format은 같이 못 써서 마지막에 한 번 더 호출)
    final = _client.chat(
        model=settings.ollama_model,
        messages=messages
        + [{"role": "user", "content": "지금까지 조회한 정보로 최종 판단을 JSON으로만 답하라."}],
        format=RESPONSE_SCHEMA,
        options={"temperature": 0},
    )
    data = json.loads(final["message"]["content"])
    trace = [_to_dict(m) for m in messages] + [_to_dict(final["message"])]
    return JudgeResult(
        is_eligible=bool(data["is_eligible"]),
        confidence=float(data["confidence"]),
        reason=str(data["reason"]),
        missing_info=list(data.get("missing_info", [])),
        trace=trace,
    )
