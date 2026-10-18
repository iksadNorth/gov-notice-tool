import datetime
import logging

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from gov_notice.crawlers.registry import CRAWLERS
from gov_notice.crawlers.run import crawl_agency
from gov_notice.db.models import Agency, Announcement
from gov_notice.db.session import SessionLocal
from gov_notice.matcher.run import run_matching
from gov_notice.notifier.run import run_notify
from gov_notice.storage import object_key, put_html

logger = logging.getLogger(__name__)


def run_crawl() -> None:
    with SessionLocal() as session:
        for code, crawler in CRAWLERS.items():
            agency = session.scalar(select(Agency).where(Agency.code == code))
            if agency is None:
                agency = Agency(code=code, name=crawler.agency_name, base_url=crawler.base_url)
                session.add(agency)
                session.flush()

            if not agency.is_active:
                continue

            details = crawl_agency(crawler, agency.last_crawled_at)
            logger.info("%s: %d건 수집", code, len(details))

            for d in details:
                key = object_key(code, d.source_url)
                put_html(key, d.content_html)

                stmt = (
                    insert(Announcement)
                    .values(
                        agency_id=agency.id,
                        source_url=d.source_url,
                        title=d.title,
                        content_text=d.content_text,
                        content_html_key=key,
                        published_at=d.published_at,
                    )
                    .on_conflict_do_update(
                        index_elements=[Announcement.agency_id, Announcement.source_url],
                        set_={
                            "title": d.title,
                            "content_text": d.content_text,
                            "content_html_key": key,
                            "published_at": d.published_at,
                        },
                    )
                )
                session.execute(stmt)

            agency.last_crawled_at = datetime.datetime.now(datetime.timezone.utc)
            session.commit()


def run_pipeline() -> None:
    run_crawl()
    with SessionLocal() as session:
        run_matching(session)
        run_notify(session)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_pipeline()
