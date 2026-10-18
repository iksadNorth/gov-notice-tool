# 시스템 구조

## 전체 구성도

```
  ┌──────────────┐                 ┌────────────────────────┐
  │ docker:ollama│                 │ host (python app)       │
  │ :11434 (기존)│◄────────────────┤ - crawler                │
  └──────────────┘                 │ - matcher (LLM)          │
                                    │ - notifier (Telegram)    │
  ┌──────────────┐                 │ - scheduler (cron)       │
  │ k8s: postgres│◄────────────────┤                           │
  │ LoadBalancer │  192.168.0.52   └────────────────────────┘
  │ :5432 (기존) │  :5432 직결
  └──────────────┘
```

- `app`은 호스트에서 직접 실행하는 Python 프로세스로 전체 파이프라인을 오케스트레이션한다.
- `ollama`는 기존 docker 컨테이너(localhost:11434) 그대로 재사용.
- **PG는 신규 컨테이너/port-forward 안 씀.** 기존 k8s postgres pod가 LoadBalancer로
  `192.168.0.52:5432`에 이미 노출돼 있어 그대로 직결한다.
  연결 문자열: `postgresql://airflow:<pw>@192.168.0.52:5432/gov_notice` (전용 DB `gov_notice`,
  비밀번호는 k8s secret `realestimate-secrets`의 `POSTGRES_PASSWORD`)
- **DB 격리**: 공유 postgres 인스턴스 안에 이 프로젝트 전용 DB(`gov_notice`)를 따로 만들어
  테이블은 그 DB의 `public` 스키마에 생성한다. 다른 워크로드와 완전히 분리되고, 필요 없어지면
  `DROP DATABASE gov_notice` 한 번으로 완전 정리 가능. (최초엔 `airflow` DB 안에 스키마만
  빌려 쓰다가 전용 DB로 분리함 — [06-roadmap.md](./06-roadmap.md) 참고)
  스키마 상세는 [03-database-schema.md](./03-database-schema.md) 참고.

## 디렉토리 구조 (제안)

uv 프로젝트로 초기화함 (`uv init --package`). 컨테이너 전환 시에도 `uv sync`로 동일 환경 재현.

```
fucking-good-game/
├── .env.example                 # DB_HOST=192.168.0.52, DB_PORT=5432, DB_NAME=gov_notice 등
├── .python-version
├── pyproject.toml
├── uv.lock
├── docs/                        # 기획/설계 문서
├── src/gov_notice/
│   ├── __init__.py
│   ├── config.py                # pydantic-settings 기반 환경변수 로드 (완료)
│   ├── storage.py               # MinIO put_object 래퍼, 멱등 오브젝트 키 생성 (완료)
│   ├── crawlers/
│   │   ├── base.py              # BaseCrawler, crawl_new (완료)
│   │   ├── fsc.py               # 금융위원회 구현체 (완료)
│   │   ├── registry.py          # CRAWLERS 등록 (완료)
│   │   └── run.py               # 백필/증분 모드 분기 crawl_agency() (완료)
│   ├── db/
│   │   ├── models.py            # SQLAlchemy 모델 (완료)
│   │   ├── session.py           # engine/SessionLocal, search_path=gov_notice 고정 (완료)
│   │   └── migrations/          # Alembic (완료, 리비전 2개 적용됨)
│   ├── matcher/                 # LLM 프롬프트, ollama 클라이언트 (미작성)
│   ├── notifier/                # Telegram 발송 (미작성)
│   └── pipeline.py              # run_crawl(): 크롤링→MinIO→PG upsert→last_crawled_at 갱신 (완료)
└── tests/
```

## 의존성 (확정)

`requests`, `beautifulsoup4`(크롤링) · `sqlalchemy`, `psycopg[binary]`, `alembic`(DB) ·
`ollama`(LLM) · `python-telegram-bot`(알림) · `apscheduler`(스케줄링) ·
`pydantic-settings`, `python-dotenv`(설정)

## 관리 페이지 (gov-notice-admin)

내 정보 CRUD, 공고 목록(페이지네이션), 공고 상세+LLM 판별 결과를 보는 웹 페이지.
파이프라인(크롤러/매처/알림)과는 별개로 **실제로 k8s 안에서 컨테이너로 도는** 첫 컴포넌트.

```
┌──────────────┐        ┌────────────────────┐        ┌──────────────┐
│ 브라우저      │──────▶│ gov-notice-admin-web│──────▶│gov-notice-   │
│ 192.168.0.60 │  :80   │ (nginx, 정적파일+   │ :8000  │admin-api     │
└──────────────┘        │  /api 리버스프록시)  │        │(FastAPI)     │
                         └────────────────────┘        └──────┬───────┘
                                                               │
                                                     postgres.default.svc
                                                     .cluster.local:5432
                                                     (gov_notice DB, in-cluster DNS)
```

- `src/gov_notice/web/main.py` — FastAPI, 라우터/서비스 레이어 분리 없이 핸들러에서 바로 DB
  접근 (소규모 관리자용 도구라 과설계 안 함)
- `src/gov_notice/web/static/*.html` — React 등 프레임워크 없이 순수 HTML/CSS/JS,
  `fetch`로 `/api/*` 호출
- 코드 컨벤션(사용자 요청): 가드 클로스 적극 사용(`if profile is None: raise ...` 먼저),
  중복 코드/분기용 메서드 추출보다 그냥 반복 허용, 변수명 정교화보다 주석으로 설명
- 이미지 2개: `gov-notice-admin-api:0.1`(FastAPI), `gov-notice-admin-web:0.1`(nginx + 정적파일)
  — `docker/admin-api/Dockerfile`, `docker/admin-web/Dockerfile`
- k8s manifest: `k8s/90-admin-api.yaml`(ClusterIP), `k8s/91-admin-web.yaml`(LoadBalancer,
  VIP `192.168.0.60` — MetalLB pool을 `.50-.59`에서 `.60`까지 확장함, 기존 풀 전부 소진 상태였음)
- **파이프라인과 DB 접속 방식이 다름**: `pipeline.py`는 호스트에서 돌아서 LAN IP(`192.168.0.52`)로
  접속하지만, 이 웹앱은 k8s 안에서 Pod로 도니까 클러스터 내부 서비스 DNS
  (`postgres.default.svc.cluster.local`)를 씀 — 전에 "컨테이너화 대비" 섹션에서 미리 메모해둔
  그 전환이 실제로 일어난 첫 사례

## 컨테이너화 대비 (차후)

지금은 호스트에서 `uv run`으로 직접 실행하지만, 추후 이 앱 자체를 컨테이너로 띄울 걸 염두에 두고
처음부터 아래 원칙을 지킨다.

- 모든 설정은 `config.py`(`pydantic-settings`)를 통한 환경변수 주입으로만 받는다.
  하드코딩된 경로/호스트 없음 → 컨테이너 이미지는 코드 불변, `.env`/k8s Secret만 바꿔 재사용
- `DB_HOST=192.168.0.52`, `MINIO_ENDPOINT=192.168.0.57:9000`는 **LAN(MetalLB LoadBalancer IP) 기준**.
  호스트에서 직접 실행 중인 지금은 문제없지만, 이 앱을 k8s 클러스터 **내부**에 Pod로 올릴 경우
  `postgres.default.svc.cluster.local` 같은 클러스터 내부 서비스 DNS로 교체 필요
  (클러스터 밖 컨테이너 — 예: 같은 호스트의 별도 docker 컨테이너 — 라면 지금 LAN IP 그대로 사용 가능)
- Dockerfile은 아직 작성하지 않음 (실제 컨테이너 전환 시점에 작성, YAGNI)

## 파이프라인 실행 흐름 (`pipeline.py`)

1. 등록된 모든 크롤러(`registry.py`)를 순회하며 신규 공고 수집
2. 신규 공고를 `announcements` 테이블에 저장 (원문 + 메타데이터)
3. 아직 판별되지 않은 공고 × 활성 사용자 프로필 조합에 대해 LLM 판별 수행
4. 판별 결과를 `matches` 테이블에 저장
5. 적합(`is_eligible = true`)으로 판정된 신규 매치에 대해 Telegram 메시지 발송
6. 발송 완료 표시 (`notified_at`) 후 종료

## 스케줄링

- 1차: 호스트 crontab 또는 `docker-compose`의 app 컨테이너 내부에서 `cron`/`APScheduler`로
  하루 1~2회(예: 09:00, 18:00) `pipeline.py` 실행
- 수동 실행도 항상 가능하도록 `python -m src.pipeline` 형태의 CLI 엔트리포인트 유지
