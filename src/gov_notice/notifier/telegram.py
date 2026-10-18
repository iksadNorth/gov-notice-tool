import logging
import time

import requests

from gov_notice.config import settings

logger = logging.getLogger(__name__)

API_URL = f"https://api.telegram.org/bot{{token}}/sendMessage"
MAX_RETRIES = 2
BACKOFF_BASE_SECONDS = 2


def build_message(
    agency_name: str,
    title: str,
    published_at,
    reason: str,
    url: str,
    is_eligible: bool = True,
    missing_info: list[str] | None = None,
) -> str:
    header = (
        f"🔔 [{agency_name}] 새 공고가 당신의 조건에 맞습니다"
        if is_eligible
        else f"❓ [{agency_name}] 조건 충족 여부를 판단할 수 없는 공고가 있습니다"
    )
    missing_block = ""
    if missing_info:
        items = "\n".join(f"- {m}" for m in missing_info)
        missing_block = f"\n\n⚠️ 정보 불충분으로 판단 못한 항목:\n{items}"

    return (
        f"{header}\n\n"
        f"제목: {title}\n"
        f"게시일: {published_at}\n"
        f"판단 근거: {reason}"
        f"{missing_block}\n\n"
        f"원문 보기: {url}"
    )


def send_message(text: str) -> bool:
    """재시도 1~2회 + 지수 백오프. 성공하면 True, 실패하면 False."""
    url = API_URL.format(token=settings.telegram_bot_token)
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                url,
                json={"chat_id": settings.telegram_chat_id, "text": text},
                timeout=10,
            )
            if resp.ok:
                return True
            logger.warning("telegram sendMessage 실패: %s", resp.text)
        except requests.RequestException as e:
            logger.warning("telegram sendMessage 예외: %s", e)

        if attempt < MAX_RETRIES:
            time.sleep(BACKOFF_BASE_SECONDS * (2**attempt))

    return False
