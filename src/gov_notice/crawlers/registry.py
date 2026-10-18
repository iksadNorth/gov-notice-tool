from gov_notice.crawlers.base import BaseCrawler
from gov_notice.crawlers.fsc import FscCrawler

CRAWLERS: dict[str, BaseCrawler] = {
    "fsc": FscCrawler(),
}
