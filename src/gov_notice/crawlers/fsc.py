import datetime

import requests
from bs4 import BeautifulSoup

from gov_notice.crawlers.base import AnnouncementDetail, AnnouncementListItem, BaseCrawler

HEADERS = {"User-Agent": "Mozilla/5.0 (gov-notice-crawler)"}


class FscCrawler(BaseCrawler):
    agency_code = "fsc"
    agency_name = "금융위원회"
    base_url = "https://www.fsc.go.kr/no010101"

    def fetch_list(self, page: int) -> list[AnnouncementListItem]:
        resp = requests.get(self.base_url, params={"curPage": page}, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        items = []
        for li in soup.select(".board-list-wrap ul > li"):
            link = li.select_one(".subject a")
            day = li.select_one(".day")
            if not link or not day:
                continue
            href = link["href"].split("?")[0]
            badge = link.select_one(".newbbs-span")
            if badge:
                badge.decompose()
            items.append(
                AnnouncementListItem(
                    source_url=f"https://www.fsc.go.kr{href}",
                    title=link.get_text(strip=True),
                    published_at=datetime.date.fromisoformat(day.get_text(strip=True)),
                )
            )
        return items

    def fetch_detail(self, item: AnnouncementListItem) -> AnnouncementDetail:
        resp = requests.get(item.source_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        cont = soup.select_one(".board-view-wrap .body .cont")
        content_html = str(cont) if cont else ""
        content_text = cont.get_text("\n", strip=True) if cont else ""

        return AnnouncementDetail(
            source_url=item.source_url,
            title=item.title,
            content_text=content_text,
            content_html=content_html,
            published_at=item.published_at,
        )
