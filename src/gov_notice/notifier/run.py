import datetime
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from gov_notice.config import settings
from gov_notice.db.models import Agency, Announcement, Match
from gov_notice.notifier.telegram import build_message, send_message

logger = logging.getLogger(__name__)


def run_notify(session: Session) -> None:
    """적합 판정(is_eligible=true, confidence 임계값 이상)인 매치만 Telegram으로 발송.

    missing_info(정보 불충분) 건은 관리 페이지 미리보기에서는 보여주지만 실제 발송은 안 함 —
    적합 여부가 불확실한 알림을 계속 보내면 알림 피로가 생겨서.
    """
    rows = session.execute(
        select(Match, Announcement, Agency)
        .join(Announcement, Match.announcement_id == Announcement.id)
        .join(Agency, Announcement.agency_id == Agency.id)
        .where(
            Match.is_eligible.is_(True),
            Match.confidence >= settings.match_confidence_threshold,
            Match.notified_at.is_(None),
        )
        .with_for_update(of=Match)
    ).all()

    for match, announcement, agency in rows:
        text = build_message(
            agency.name,
            announcement.title,
            announcement.published_at.date() if announcement.published_at else None,
            match.reason,
            announcement.source_url,
            is_eligible=match.is_eligible,
            missing_info=match.missing_info,
        )
        if send_message(text):
            match.notified_at = datetime.datetime.now(datetime.timezone.utc)
            session.commit()
            logger.info("notified match=%s", match.id)
        else:
            logger.error("notify 실패, 다음 배치에서 재시도: match=%s", match.id)
            session.rollback()
