import datetime

from gov_notice.crawlers.base import AnnouncementDetail, BaseCrawler

BACKFILL_SINCE = datetime.date(2000, 1, 1)
BACKFILL_MAX_PAGES = 200
INCREMENTAL_MAX_PAGES = 5


def crawl_agency(
    crawler: BaseCrawler, last_crawled_at: datetime.datetime | None
) -> list[AnnouncementDetail]:
    """last_crawled_at이 None이면 백필(전체), 있으면 그 시점 이후만 증분 수집.

    ponytail: 모드별 메서드 따로 안 만듦, crawl_new에 파라미터만 다르게 넘긴다.
    """
    if last_crawled_at is None:
        return crawler.crawl_new(since=BACKFILL_SINCE, max_pages=BACKFILL_MAX_PAGES)
    return crawler.crawl_new(since=last_crawled_at.date(), max_pages=INCREMENTAL_MAX_PAGES)
