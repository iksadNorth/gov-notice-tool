import datetime
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AnnouncementListItem:
    source_url: str
    title: str
    published_at: datetime.date


@dataclass
class AnnouncementDetail:
    source_url: str
    title: str
    content_text: str
    content_html: str
    published_at: datetime.date


class BaseCrawler(ABC):
    agency_code: str
    agency_name: str

    @abstractmethod
    def fetch_list(self, page: int) -> list[AnnouncementListItem]:
        """게시판 목록 페이지 1장에서 공고 항목을 추출한다."""

    @abstractmethod
    def fetch_detail(self, item: AnnouncementListItem) -> AnnouncementDetail:
        """상세 페이지에서 본문(텍스트/HTML)을 추출한다."""

    def crawl_new(
        self, since: datetime.date, max_pages: int = 5
    ) -> list[AnnouncementDetail]:
        """since보다 최신인 공고만 모아서 상세까지 가져온다.

        ponytail: since보다 오래된 글이 한 페이지라도 나오면 그 페이지에서 멈춘다.
        게시판이 최신순 정렬이라는 전제 — 다른 정렬이면 이 가정 깨짐.
        """
        results = []
        for page in range(1, max_pages + 1):
            items = self.fetch_list(page)
            if not items:
                break
            stop = False
            for item in items:
                if item.published_at < since:
                    stop = True
                    break
                results.append(self.fetch_detail(item))
            if stop:
                break
        return results
