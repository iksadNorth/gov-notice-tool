# 크롤러 설계

## 설계 목표

처음에는 금융위원회(fsc.go.kr) 보도자료 게시판 1곳만 지원하지만, 향후 다수의 공공기관으로
확장될 것을 전제로 "사이트마다 다른 HTML 구조"를 흡수할 수 있는 플러그인 구조로 만든다.

## 1호 크롤링 대상

- 기관: 금융위원회
- URL 예시: `https://www.fsc.go.kr/no010101/87726?srchCtgry=&curPage=&srchKey=&srchText=&srchBeginDt=&srchEndDt=`
- 목록 페이지(게시판) → 상세 페이지(개별 공고) 2단계 구조로 추정됨 (실제 구현 시 HTML 구조 분석 필요)

## 공통 인터페이스 (`BaseCrawler`)

모든 기관 크롤러는 아래 인터페이스를 구현한다.

```python
class BaseCrawler(ABC):
    agency_code: str       # 예: "fsc" (금융위원회)
    agency_name: str       # 예: "금융위원회"

    @abstractmethod
    def fetch_list(self, page: int) -> list[AnnouncementListItem]:
        """게시판 목록 페이지에서 공고 항목(제목, 상세 URL, 게시일 등) 추출"""

    @abstractmethod
    def fetch_detail(self, item: AnnouncementListItem) -> AnnouncementDetail:
        """상세 페이지에서 본문, 첨부파일 링크 등 추출"""

    def crawl_new(self, since: datetime) -> list[AnnouncementDetail]:
        """since 이후 게시된 신규 공고만 반환 (공통 로직, 재정의 불필요)"""
```

- 기관별 구현체(`fsc.py`, 향후 `moel.py` 등)는 `fetch_list`/`fetch_detail`의 HTML 파싱 부분만 구현
- 중복 수집 방지는 `agency_code + 원문 URL`을 유니크 키로 사용 (DB 레벨 unique 제약)

## 크롤러 등록 구조 (`registry.py`)

```python
CRAWLERS: dict[str, BaseCrawler] = {
    "fsc": FscCrawler(),
    # "moel": MoelCrawler(),  # 향후 고용노동부 추가 예시
}
```

- 신규 기관 추가 시 `crawlers/<agency>.py`에 구현체 작성 후 `registry.py`에 한 줄 등록하면 끝
- 기관별 크롤링 주기/활성화 여부는 DB의 `agencies` 테이블에서 관리 (코드 수정 없이 on/off 가능)

## 크롤링 방식 선택 기준

- 기본: `requests` + `BeautifulSoup` (정적 HTML)
- 목록/상세가 JS 렌더링에 의존하는 사이트라면 해당 크롤러에서만 Playwright로 대체
  → `BaseCrawler`는 구현 방식을 강제하지 않으므로 사이트별로 자유롭게 선택 가능

## 예의 있는 크롤링 (Rate Limiting)

- 기관별 요청 간 최소 딜레이(예: 1~2초) 설정
- User-Agent 명시, robots.txt 준수 여부 확인
- 과도한 동시 요청 금지 (기관별 순차 처리 또는 낮은 동시성)

## fsc.go.kr 실제 구조 (확인 완료)

처음 전달받은 URL(`/no010101/87726?...`)은 사실 **상세 페이지**였음 (87726 = 글 번호).
실제 목록 페이지는 `/no010101?curPage={n}` (id 없음).

- 목록: `.board-list-wrap ul > li` 반복, 각 항목에서
  - 제목/링크: `.subject a` (href, title) — `.newbbs-span`("금일 등록된 게시글" 배지)는
    텍스트에 섞여 들어가므로 `get_text()` 전에 decompose 필요
  - 게시일: `.day` (예: `2026-10-01`, `date.fromisoformat`로 바로 파싱 가능)
- 상세: `/no010101/{id}?...`
  - 제목: `.subject`
  - 본문: `.board-view-wrap .body .cont` (텍스트+HTML 둘 다 여기서 추출)
  - "이전글/다음글" 네비게이션 있음(페이지네이션 용도 아님)

`src/gov_notice/crawlers/fsc.py`에 구현 완료, 실제 사이트 대상으로 목록 10건 + 상세 1건
파싱 검증함.

## 최초 적재(백필) 계획

`crawl_new(since, max_pages)`는 이미 "빈 페이지 나오면 멈춤" 로직이 있어서, 백필도 같은 메서드를
파라미터만 다르게 줘서 재사용한다 (`src/gov_notice/crawlers/run.py`의 `crawl_agency`).

| 상황 | 판단 기준 | since | max_pages |
|---|---|---|---|
| 최초 백필 | `agencies.last_crawled_at IS NULL` | 아주 과거 날짜(2000-01-01) | 200 (안전캡, 보통 빈 페이지에서 먼저 멈춤) |
| 평소 증분 | `last_crawled_at` 값 있음 | 그 값 | 5 |

- `agencies`에 `last_crawled_at`(nullable) 컬럼 추가함 — 기관별로 상태 추적
  (처음 등록된 기관은 NULL → 자동으로 백필 모드)
- 배치 1회 실행 끝날 때마다 `last_crawled_at = now()`로 갱신 (pipeline.py 책임)
- `BACKFILL_MAX_PAGES=200`은 안전장치일 뿐 — 실제로는 목록이 빈 페이지를 반환하는 순간
  멈추므로 그 기관의 전체 게시물 수가 200페이지(약 2000건)보다 적으면 끝까지 다 가져옴

## 열린 질문

- 첨부파일(PDF/HWP) 내용까지 LLM 판별에 활용할지 여부는 1차 범위에서는 제외, 제목+본문 텍스트만 사용
- 목록이 항상 최신순 정렬이라는 전제로 `crawl_new`가 "오래된 글 나오면 중단" 로직을 씀 —
  정렬이 바뀌면 깨짐, 당장은 fsc.go.kr 기준 정상 동작 확인
