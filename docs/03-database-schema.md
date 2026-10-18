# 데이터베이스 스키마 (PostgreSQL)

## DB 격리

기존 k8s postgres pod(공유 인스턴스)를 재사용하되, 전용 데이터베이스 `gov_notice`를 따로
만들어 그 안의 `public` 스키마에 테이블을 둔다. (최초엔 `airflow` DB 안에 `gov_notice`
스키마만 빌려 쓰는 구조였다가, 관리 페이지를 만들면서 전용 DB로 분리함 —
[06-roadmap.md](./06-roadmap.md) "전용 스키마 → 전용 DB로 분리" 참고.) 다른 워크로드와
완전히 분리되고, 필요 없어지면 `DROP DATABASE gov_notice` 한 번으로 흔적 없이 제거 가능.

```sql
CREATE DATABASE gov_notice OWNER airflow;
\c gov_notice
CREATE EXTENSION vector;
```

아래 모든 테이블은 `gov_notice` DB의 `public` 스키마에 그냥 생성한다 (스키마 접두어 불필요).

## ERD 요약

```
agencies ──< announcements ──< matches >── user_profiles
```

## 테이블 정의

### `agencies` — 크롤링 대상 기관

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | serial PK | |
| code | text UNIQUE | 예: "fsc" |
| name | text | 예: "금융위원회" |
| base_url | text | 게시판 목록 URL |
| is_active | boolean | 크롤링 활성화 여부 |
| last_crawled_at | timestamptz nullable | 마지막 크롤링 시각. NULL이면 아직 한 번도 안 돈 기관 → 백필 모드 트리거 ([02-crawler.md](./02-crawler.md)) |
| created_at | timestamptz | |

### `announcements` — 수집된 공고 원문

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | serial PK | |
| agency_id | int FK → agencies | |
| source_url | text | 상세 페이지 URL |
| title | text | 제목 |
| content_text | text | 본문 텍스트(LLM 입력용 파싱 결과, PG에 그대로 저장 — 크기 작음) |
| content_html_key | text | MinIO 오브젝트 키 (원문 HTML, 재파싱 대비 보존 — 용량 커서 PG 밖으로 분리) |
| published_at | timestamptz | 공고 게시일 |
| crawled_at | timestamptz | 수집 시각 |
| UNIQUE | (agency_id, source_url) | 중복 수집 방지, 멱등키 |

#### HTML 원문 저장 — MinIO

`content_html`은 PG 대신 MinIO(k8s `default/minio`, 192.168.0.57:9000)에 저장한다. PG에는
오브젝트 키만 문자열로 보관.

- 버킷: `gov-notice-raw` (크롤러 최초 실행 시 없으면 생성)
- 오브젝트 키 규칙: `{agency_code}/{sha256(source_url)}.html`
  → `source_url` 해시 기반이라 같은 공고 재크롤링 시 같은 키에 덮어쓰기 = 자연히 멱등
- PG 저장 직전에 MinIO put 먼저 수행, 성공한 키만 `content_html_key`에 기록
  (PG row가 가리키는 키는 항상 실존 보장)

### `user_profiles` — (삭제됨, `profile_facts`로 통합)

원래 원본 데이터(jsonb)를 `user_profiles`에, 검색용 파생 데이터를 `profile_facts`에 나눠
저장했는데, 두 군데로 쪼개진 게 혼란스러워서 `profile_facts` 하나로 합쳤다. 자세한 배경은
[06-roadmap.md](./06-roadmap.md) "user_profiles + profile_facts → profile_facts 하나로
통합" 참고. 아래 `profile_facts` 설명 참고.

### `matches` — LLM 판별 결과

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | serial PK | |
| announcement_id | int FK → announcements | |
| profile_label | text | 프로필 구분명 (FK 아님, `profile_facts.profile_label`과 느슨하게 연결) |
| is_eligible | boolean | 적합 여부 |
| confidence | numeric | LLM이 제시한 확신도(0~1), 선택적 |
| reason | text | LLM이 제시한 판단 근거 |
| missing_info | jsonb | LLM이 못 찾은 정보 목록 (빈 배열이면 없음) |
| trace_key | text nullable | MinIO에 저장된 LLM 대화 로그 오브젝트 키 |
| model_name | text | 사용된 ollama 모델명 (재현성/비교용) |
| judged_at | timestamptz | 판별 시각 |
| notified_at | timestamptz nullable | Telegram 발송 시각 (NULL이면 미발송) |
| UNIQUE | (announcement_id, profile_label) | 동일 조합 중복 판별 방지 |

### `profile_facts` — 프로필 정보 + 임베딩 (유일한 프로필 저장소)

공고마다 요구 조건이 제각각이라 "어떤 필드가 필요한지" 확정 지을 수 없고, LLM이
`query_profile` 툴로 필요한 키만 그때그때 조회하는 구조라 고정 컬럼이 필요 없다. 원래
원본(jsonb)과 검색용 파생 테이블로 나뉘어 있었는데 하나로 합침
([06-roadmap.md](./06-roadmap.md) 참고) — `profile_label`이 "프로필 이름" 역할을 겸하고,
같은 label을 가진 행들이 모여서 한 프로필을 이룬다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| id | serial PK | |
| profile_label | text | 프로필 이름 (예: "본인") — 같은 label 행들이 한 프로필 |
| key | text | 한글로 저장 (예: `월급`) — 영문 변수명 아님, 쿼리도 한글이라 번역 매핑 계층 불필요 |
| value_text | text | 값을 문자열화한 것 |
| embedding | vector(768) | `nomic-embed-text` 임베딩, pgvector 타입. `<=>` 연산자로 유사도 검색 |
| is_active | boolean | 판별 대상 여부 (같은 label의 모든 행에 중복 저장됨, 프로필 단위 플래그라 어쩔 수 없음) |
| updated_at | timestamptz | |
| UNIQUE | (profile_label, key) | 멱등 upsert 키 |

쓰기는 `matcher/profile_store.py`의 `upsert_profile()`/`delete_profile()`을 통해서만 한다
(웹 CRUD가 직접 호출). 조회는 `query_profile_facts()` — 자세한 설계 배경은
[04-llm-matching.md](./04-llm-matching.md) "프로필 능동 쿼리 인터페이스" 참고.

## 인덱스

- `announcements(agency_id, published_at)` — 최신순 조회
- `matches(is_eligible, notified_at)` — 미발송 적합 건 조회용

## 멱등성 계획

파이프라인(크롤링→저장→판별→알림) 전 단계가 같은 입력으로 몇 번을 다시 돌려도 결과가 같아야
한다. `source_url` 단독은 멱등키로 부족 — 기관이 늘어나면 서로 다른 기관의 URL 경로가 우연히
겹칠 수 있다. 그래서 각 단계마다 복합키를 쓴다.

| 단계 | 멱등키 | 처리 방식 |
|---|---|---|
| 크롤링→저장 | `(agency_id, source_url)` | `INSERT ... ON CONFLICT (agency_id, source_url) DO UPDATE` — 재크롤링 시 title/content만 갱신, id는 유지 |
| HTML→MinIO | `sha256(source_url)` (오브젝트 키) | 같은 키 재업로드 = 덮어쓰기, PUT은 그 자체로 멱등 |
| LLM 판별→저장 | `(announcement_id, profile_label)` | `INSERT ... ON CONFLICT (announcement_id, profile_label) DO NOTHING` — 이미 판별된 조합은 LLM 재호출 자체를 스킵 (비용 절감) |
| Telegram 발송 | `matches.notified_at IS NULL` 을 발송 대상 조건으로, 발송 성공 시에만 값 채움 | 발송 전 `SELECT ... FOR UPDATE`로 동시 실행 중복 발송 방지 |

- 모든 UNIQUE 제약은 PG 레벨에서 강제 (애플리케이션 버그로 중복 들어가는 것 자체를 DB가 차단)
- 배치가 중간에 죽어도 재실행하면 이미 처리된 건은 건너뛰고 미처리 건만 이어서 처리됨

## 마이그레이션 도구

- Alembic 사용 (SQLAlchemy 모델과 1:1 대응)
