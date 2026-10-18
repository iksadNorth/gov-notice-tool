import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gov_notice.config import settings
from gov_notice.db.models import Announcement, Match
from gov_notice.matcher.ollama_client import judge
from gov_notice.matcher.profile_store import list_profile_labels
from gov_notice.storage import put_json, trace_key

logger = logging.getLogger(__name__)


def run_matching(session: Session) -> None:
    """아직 판별 안 된 (announcement, 활성 프로필) 조합만 LLM 호출.

    ponytail: announcement/profile 둘 다 적은 POC 규모라 바깥쪽 LEFT JOIN 대신
    그냥 이중 루프 + 존재 체크. 개수 늘면 그때 쿼리 최적화.
    """
    announcements = session.scalars(select(Announcement)).all()
    profile_labels = list_profile_labels(session, active_only=True)

    for ann in announcements:
        for profile_label in profile_labels:
            exists = session.scalar(
                select(Match.id).where(
                    Match.announcement_id == ann.id,
                    Match.profile_label == profile_label,
                )
            )
            if exists:
                continue

            result = judge(ann.title, ann.content_text, profile_label)
            logger.info(
                "judged ann=%s profile=%s -> %s (%.2f)",
                ann.id,
                profile_label,
                result.is_eligible,
                result.confidence,
            )

            key = trace_key(ann.id, profile_label)
            put_json(key, result.trace)

            stmt = (
                insert(Match)
                .values(
                    announcement_id=ann.id,
                    profile_label=profile_label,
                    is_eligible=result.is_eligible,
                    confidence=result.confidence,
                    reason=result.reason,
                    missing_info=result.missing_info,
                    trace_key=key,
                    model_name=settings.ollama_model,
                )
                .on_conflict_do_nothing(
                    index_elements=[Match.announcement_id, Match.profile_label]
                )
            )
            session.execute(stmt)
            session.commit()
