# 개발 로드맵 & 열린 결정 사항

## 단계별 로드맵

### Phase 0 — 환경 구성
- [x] k8s postgres pod 확인 (`default/postgres`), LoadBalancer(192.168.0.52:5432) 직결 확인
- [x] k8s minio pod 확인 (`default/minio`), LoadBalancer(192.168.0.57:9000) 확인
- [x] `gov_notice` 스키마 생성 완료 (DB: `airflow`, owner: `airflow`)
- [x] MinIO 버킷 `gov-notice-raw` 생성 완료 (다른 워크로드 버킷과 분리, root 계정 `realestimate-secrets`로 생성 — 운영 전환 시 전용 access key 발급 검토)
- [x] Python 프로젝트 초기화 완료 (`uv init --package`, `src/gov_notice/` 레이아웃, 핵심 의존성 설치)
- [x] `.env.example` 작성 완료, `config.py`(pydantic-settings) 로드 검증 완료

### Phase 1 — DB & 프로필
- [x] SQLAlchemy 모델 작성 (`src/gov_notice/db/models.py`, schema="gov_notice" 고정)
- [x] Alembic 설정 + 초기 리비전 생성/적용 완료 — 테이블 4개(agencies/announcements/user_profiles/matches) 생성됨
  - ⚠️ 공유 DB 재사용 구조라 `env.py`에 `include_name` 필터 필수. 필터 없이 autogenerate 돌렸다가
    mlflow/airflow 등 남의 테이블이 전부 "삭제 대상"으로 잡힌 사고 있었음 — 실행 전 발견해서 폐기함.
    앞으로 autogenerate 결과는 반드시 diff 확인 후 적용.
- [ ] 본인 프로필(`user_profiles`) 수동 입력 스크립트 또는 CLI

### Phase 2 — 크롤러 (fsc.go.kr)
- [x] fsc.go.kr 목록/상세 HTML 구조 분석 완료 ([02-crawler.md](./02-crawler.md) 참고 — 처음 받은 URL이
  실은 상세 페이지였음, 목록은 `/no010101?curPage={n}`)
- [x] `BaseCrawler` 인터페이스 구현 (`src/gov_notice/crawlers/base.py`)
- [x] `FscCrawler` 구현 완료, 실제 사이트로 목록/상세 파싱 검증 완료 (`src/gov_notice/crawlers/fsc.py`)
- [x] 최초 백필 계획 수립 완료 — `agencies.last_crawled_at` 컬럼 추가(마이그레이션 적용됨),
  `crawl_agency()`로 백필/증분 모드 분기 ([02-crawler.md](./02-crawler.md) 참고)
- [x] `pipeline.py` 연동 완료: 크롤링 → MinIO HTML 업로드(`storage.py`) → PG upsert
  (`ON CONFLICT (agency_id, source_url) DO UPDATE`) → `agencies.last_crawled_at` 갱신
  - 실제 fsc.go.kr 대상 10건 end-to-end 검증 완료 (PG row 수 = MinIO 오브젝트 수 일치)
  - 동일 데이터 재실행해도 row 안 늘어나는 것(멱등) 확인 완료
- [x] `db/session.py` 추가 — engine에 `search_path=gov_notice` 고정, 테이블명에 스키마 접두어 안 써도 됨
- [x] MinIO 연동은 수작업 SigV4 대신 `uv add minio` 패키지 사용으로 단순화
  (시스템 `pip`은 막혀 있었지만 `uv`는 프로젝트 격리 환경이라 정상 동작)

### Phase 3 — LLM 판별
- [x] 로컬 ollama에 `qwen2.5:14b-instruct-q4_K_M` 모델 확인, `.env`에 반영
- [x] `matcher/prompt.py` — system/user 프롬프트 + JSON 스키마(`RESPONSE_SCHEMA`) 작성
- [x] `matcher/ollama_client.py` — `format=RESPONSE_SCHEMA`로 구조화 출력 강제, `JudgeResult` 반환
- [x] 샘플 2건(적합/부적합)으로 판별 정확도 검증 완료 — 둘 다 기대대로 판정, 근거도 조건을 정확히 짚음
  (단, 14b 모델이라 응답에 1~2분 소요 — 공고×프로필 수 많아지면 배치 소요시간 고려 필요)
- [x] `matches` 테이블 저장 연동 완료 — `matcher/run.py`의 `run_matching()`,
  announcement × active user_profile 조합 순회 + 이미 판별된 조합 스킵 + `ON CONFLICT DO NOTHING`,
  건별 즉시 commit(크래시 내성). `pipeline.run_pipeline()`에서 크롤링 뒤에 바로 연결함.
  실 DB 저장까지 end-to-end 검증 완료 (자격요건 불명확 공고 → confidence 0.3으로 보수적 처리 확인)

### Phase 4 — Telegram 알림
- [x] 봇 생성(`@gov_notice_alert_bot`), 토큰/chat_id 확보해 `.env`에 반영
- [x] `notifier/telegram.py` — `send_message()`, 실패 시 재시도 2회 + 지수 백오프
- [x] `notifier/run.py` — `is_eligible AND confidence>=임계값 AND notified_at IS NULL`인 매치만
  조회해 발송, 성공 시에만 `notified_at` 갱신. `MATCH_CONFIDENCE_THRESHOLD`(기본 0.5) 설정값 추가
- [x] `pipeline.run_pipeline()`에 크롤링→판별→알림 전체 연결 완료
- [x] 실제 텔레그램으로 메시지 수신 확인, 재실행해도 중복 발송 안 되는 것(멱등) 확인 완료
- 참고: `python-telegram-bot` 의존성은 과함 — `sendMessage`는 `requests.post` 한 줄이면 충분해서
  제거하고 직접 호출로 구현함

### Phase 5 — 파이프라인 통합 & 스케줄링
- [ ] `pipeline.py`로 전체 흐름 연결
- [ ] cron/APScheduler로 정기 실행 설정
- [ ] 로깅/에러 알림(파이프라인 자체 실패 시에도 Telegram으로 알림 고려)

### Phase 6 — 확장 (1차 완료 후)
- [ ] 2번째 기관 크롤러 추가해 플러그인 구조 검증
- [ ] 다중 사용자/프로필 지원 여부 검토

## 완료 — user_profiles + profile_facts → profile_facts 하나로 통합 (2026-10-09)

**배경**: 같은 프로필 데이터가 `user_profiles`(원본 jsonb)와 `profile_facts`(검색용 파생
key-value+임베딩)로 두 군데에 쪼개져 있던 게 혼란스럽다는 피드백. `profile_facts` 하나로
합침 — `profile_label`(문자열)이 이제 "프로필 이름" 역할을 겸함, 같은 label의 행들이 한 프로필.

**변경**:
- `profile_facts`에 `profile_label`, `is_active` 컬럼 추가(같은 label 행마다 중복 저장되지만
  프로필 단위 플래그라 어쩔 수 없음), `user_profile_id`/FK 제거
- `matches.user_profile_id`(FK) → `matches.profile_label`(문자열, FK 없음)로 교체
- `user_profiles` 테이블 완전히 삭제
- 데이터 변환 포함한 수동 Alembic 마이그레이션 작성(autogenerate 대신 — 변환 로직이 있어서
  직접 제어 필요) — 기존 데이터(프로필 1개, facts 4개, matches 10개) 전부 보존하며 이전 완료
- `matcher/profile_store.py` 재작성: `sync_profile_facts` 삭제, 대신
  `list_profile_labels`/`get_profile`/`upsert_profile`/`delete_profile` 제공 (웹 CRUD가
  이걸 직접 호출, 더 이상 "원본→파생 동기화" 단계 자체가 없음)
- `web/main.py` 프로필 CRUD를 label 기준으로 재작성 (PK가 id 아니라 label)
- `matcher/run.py`/`mcp_server.py`도 `UserProfile` 의존성 제거, `profile_label` 직접 사용
- 로컬에서 CRUD 왕복(생성→조회→삭제) + MCP 쿼리 + 웹 API 전체 재검증 후 배포

## 완료 — 로컬 docker 레지스트리로 이미지 배포 단순화 (2026-10-09)

**배경**: k3s가 이미지를 containerd로 관리해서 `docker build`로 만든 이미지가 바로 안 보임.
그래서 매번 `docker save` → `--privileged --pid=host nsenter`로 호스트 진입 →
`k3s ctr images import` 하는 번거로운 과정을 거쳤었음. (Claude Code 샌드박스가
`--privileged --pid=host`를 "Containment Escape"로 막아서 이 단계는 항상 사용자가 직접
실행해야 했음.)

**조치**:
- 호스트에 `registry:2` 컨테이너를 **k8s pod가 아니라 평범한 docker 컨테이너로** 띄움
  (`localhost:5000`) — 이건 애플리케이션이 아니라 "로컬 빌드 → k3s 전달" 사이의 빌드 도구라
  k8s가 관리할 이유가 없음. 데이터는 `/mnt/t7/registry`에 저장(루트 파티션 39G밖에 안 남아서
  거기 안 씀, `/mnt/t7`은 737G 여유)
- `/etc/rancher/k3s/registries.yaml`에 `localhost:5000`을 insecure(HTTP) 레지스트리로 등록,
  k3s 재시작 (시스템 설정 파일이라 사용자가 직접 — 저는 여기도 접근 불가)
- `k8s/90-admin-api.yaml`, `k8s/91-admin-web.yaml`의 `image:`를
  `localhost:5000/gov-notice-*:0.1`로, `imagePullPolicy: Never` → `Always`로 변경
- `crictl pull`로 k3s가 레지스트리에서 직접 pull 받는 것 검증, 실제 재배포까지 성공
- 앞으로 이미지 갱신: `docker build` → `docker push localhost:5000/...` →
  `kubectl rollout restart` 세 줄로 끝남 (save/nsenter/import 단계 전부 제거됨)
- realestimate 프로젝트(postgres/airflow 등)도 같은 import 방식을 쓰고 있어서, 이 레지스트리
  생기면 거기도 같이 혜택 봄 (아직 그쪽 manifest는 안 바꿈 — 필요시 나중에)

## 완료 — 관리 페이지 (gov-notice-admin) (2026-10-09)

- FastAPI 백엔드(`src/gov_notice/web/main.py`) + 순수 HTML/CSS/JS 프론트(`src/gov_notice/web/static/`)
  — 내 정보 CRUD, 공고 목록(페이지네이션), 공고 상세+LLM 판별 결과 3개 페이지
- nginx가 정적 파일 서빙 + `/api` 리버스프록시, LoadBalancer VIP `192.168.0.60`으로 노출
  (MetalLB pool 기존 `.50-.59` 전부 소진 → `.60`까지 확장)
- 로컬 docker 네트워크로 전체 체인(브라우저→nginx→FastAPI→PG) 먼저 검증 후 k8s 배포
- 상세: [01-architecture.md](./01-architecture.md) "관리 페이지" 참고
- 참고: 지금 **인증 없음** — LAN 안에서 VIP 아는 사람 누구나 접근 가능(실제 개인정보 포함).
  외부 노출 계획 있으면 Basic Auth 등 추가 필요 (지금은 집 LAN 한정이라 미보류)

## 완료 — 전용 스키마 → 전용 DB로 분리 (2026-10-09)

**배경**: 지금까지 `airflow` DB 안에 `gov_notice` 스키마를 빌려 쓰는 구조였음(다른 워크로드와
같은 DB 공유). 관리 페이지(아래 항목)를 만들면서 더 깔끔하게 분리하기로 함 — 전용 DB
`gov_notice`를 새로 만들고 테이블들을 그 DB의 `public` 스키마로 옮김.

**이전 작업**:
- `CREATE DATABASE gov_notice OWNER airflow;` + `CREATE EXTENSION vector;`
- `pg_dump -n gov_notice -d airflow`로 기존 데이터 전체 덤프 → 스키마 접두어(`gov_notice.`) 제거,
  `search_path` 빈 값 → `public`으로 수정 → 신규 DB에 복원
  - 삽질: pg_dump가 보안상 `SET search_path = ''`를 넣어두는데 이걸 못 보고 접두어만 지웠다가
    "no schema has been selected to create in" 에러로 전체 복원 실패 → search_path를 public으로
    고쳐서 해결
  - 삽질 2: pg16+ dump의 `\restrict`/`\unrestrict` 가드 메타커맨드가 이 psql 세션에서
    거부되면서 COPY 블록까지 깨짐 → 해당 줄 제거
- 복원 후 row 수 전부 원본과 일치 확인(announcements 10, matches 10, user_profiles 1,
  profile_facts 4, agencies 1), `alembic current`도 head와 일치 확인
- 코드에서 스키마 분리 로직 전부 제거: `models.py`(`MetaData(schema=...)` → 기본값),
  `ForeignKey`에서 스키마 접두어 제거, `db/session.py`(`search_path` connect_args 제거),
  `config.py`(`db_schema_` 필드 제거), `alembic/env.py`(`include_name` 필터·
  `version_table_schema` 등 공유 DB 대응 코드 전부 제거 — 이제 전용 DB라 불필요)
- `.env`/`.env.example`: `DB_NAME=gov_notice`로 변경, `DB_SCHEMA` 삭제

## 완료 — MinIO → SeaweedFS 전환 (2026-10-03)

**배경**: MinIO가 2025년 10월부터 커뮤니티 에디션 사전 빌드 배포(이미지/바이너리)를 전부 중단,
2026년 9월 11일 `minio/minio`/`minio/mc`가 Docker Hub·Quay.io 양쪽에서 완전 삭제됨
(`docker login` 해도 "repository does not exist", 바이너리도 `410 Gone`). 공유 k8s의 기존
MinIO pod가 재시작되며 이미지를 다시 못 받아와 장애 발생 — 이 프로젝트가 원인이 아니라
외부 요인으로 터진 장애.

**영향 범위**: 이 MinIO는 `gov_notice` 전용이 아니라 Airflow XCom 백엔드/task 로그 저장소로도
쓰이고 있어서 ([`k8s/README.md`](../../../realestimate/k8s/README.md)), 단순 교체가 아니라
Airflow까지 같이 고려해야 했음.

**조치** (`/home/iksadnorth/project/realestimate/k8s/`):
- `12-minio.yaml`: 컨테이너 이미지를 `chrislusf/seaweedfs:latest`(S3 호환, Apache-2.0,
  활발히 유지보수)로 교체. `weed server -s3 -filer`로 단일 컨테이너에서 S3 API(9000) 제공.
  Service 이름(`minio`)·VIP(192.168.0.57)·포트(9000) 유지 → Airflow 쪽 연결 설정 변경 불필요
  - 삽질: `-ip=minio`로 주면 weed가 Service ClusterIP로 bind 시도해서
    `bind: cannot assign requested address`로 크래시 → `-ip=localhost -ip.bind=0.0.0.0`으로 수정
  - hostPath를 `/mnt/t7/minio`에서 `/mnt/t7/seaweedfs`로 분리 (데이터 포맷 다름, 기존 MinIO
    데이터와 섞이면 안 됨 — 사실상 새로 시작, 기존 버킷 내용은 소실)
- `13-minio-init-job.yaml`: `minio/mc`도 삭제돼서 `amazon/aws-cli`(S3 API 호환, 별도 배포
  채널)로 교체. `aws s3`/`s3api` 명령으로 버킷 생성 + lifecycle 설정
- 이미지 pull/save는 제가 직접(`docker pull`, `docker save`), k3s containerd import와
  `kubectl apply`는 "Modify/Containment" 샌드박스 제약으로 사용자가 직접 실행
- 결과: `airflow-xcom`, `airflow-logs`, `gov-notice-raw` 버킷 재생성 완료, 업로드/다운로드
  왕복 테스트 통과, `gov_notice` 파이프라인 전체(크롤링→MinIO→LLM→trace 저장→알림) 재검증 완료

## 완료 — 공유 postgres에 pgvector / pg_stat_statements 설치 (2026-10-03)

- `/home/iksadnorth/project/realestimate/docker/postgres/apt-extensions.txt`에
  `postgresql-16-pgvector` 추가, 이미지 재빌드 → k3s containerd import → `k8s/10-postgres.yaml`
  재적용(`shared_preload_libraries=pg_stat_statements` args도 같이 추가)
- 이미지 빌드/확인(`docker build`, `docker run`으로 vector.so 확인)은 제가 직접 했고,
  k3s containerd import(`--privileged --pid=host` 필요)는 샌드박스가 "Containment Escape"로
  차단해서 사용자가 직접 실행함
- 결과: `airflow` DB에 `vector` 확장, `postgres` DB에 `pg_stat_statements` 확장 설치 확인,
  새 pod 정상 기동 확인
- `docker/postgres/init/03-create-extensions.sql`에도 반영해둬서 다음에 PGDATA를 새로 만들 때는
  자동으로 적용됨 (기존 PGDATA는 init 스크립트가 재실행 안 되므로 이번엔 수동으로 생성함)
- pg_stat_statements는 이번 프로젝트에서 바로 쓰진 않음 — 다른 워크로드 쿼리 성능 조회용으로
  요청받아 같이 설치
- `profile_facts.embedding`을 pgvector `vector` 타입+`<=>` 연산자로 실제 전환 완료
  (아래 "프로필 쿼리 인터페이스 재설계" 항목에서 같이 진행함)

## 완료 — 프로필 쿼리 인터페이스 재설계: 대칭 임베딩 + 한글 키 + pgvector (2026-10-03)

- 문제 제기: ①쿼리를 문장으로 받는데 저장은 명사형이라 의미 공간 불일치, ②`search_query:`/
  `search_document:`는 질문→문서 비대칭 검색용이라 명사-명사 매칭엔 부적합, ③영문 key와
  한글 쿼리 사이 번역 레이어(`KEY_LABELS`)가 비용/복잡도만 늘림
- 해결: MCP `query`를 명사/키워드로 제한, 임베딩을 대칭 방식(`clustering:` 프리픽스 하나로
  통일)으로 변경, `user_profiles.data`/`profile_facts.key`를 한글로 전환해 `KEY_LABELS` 삭제
- `profile_facts.embedding`을 `ARRAY(Float)` → `Vector(768)`(pgvector)로 마이그레이션,
  Python 코사인 루프 삭제하고 `<=>` 연산자로 DB 레벨 정렬
- 삽질 2건 기록: (1) `vector` 타입이 `public` 스키마에 있어서 `search_path=gov_notice`만으론
  "operator does not exist" 남 → `search_path=gov_notice,public`으로 수정.
  (2) 벡터를 그냥 list로 바인딩하면 타입 추론 안 돼서 `<=> unknown` 에러 →
  `literal(vec, type_=Vector(768))`로 명시 캐스팅 필요
- 결과: 테스트 쿼리 5개 중 4개 top-1 정확 매칭, 점수 분리도 뚜렷해짐(이전 0.6~0.7대 뭉침 →
  동일어 1.0/유사 0.9대/그 외 낮음)
- 상세: [04-llm-matching.md](./04-llm-matching.md) "쿼리/저장 방식 — 비대칭 → 대칭으로 수정" 참고

## 완료 — 프로필 능동 쿼리 MCP 툴 (2026-10-02)

- `gov_notice.profile_facts` 테이블 추가(마이그레이션 적용됨) — key-value + 임베딩(float[])
- ollama `nomic-embed-text` pull 완료, `search_query:`/`search_document:` 프리픽스 적용
  (안 붙이면 변별력 떨어지는 버그 직접 겪고 수정함)
- `matcher/embeddings.py`, `matcher/profile_store.py`, `matcher/mcp_server.py`(`mcp` v2 SDK)
  구현 완료, 실제 쿼리("나이", "월급 얼마나 받아" 등)로 검증 완료
- 상세: [04-llm-matching.md](./04-llm-matching.md) "프로필 능동 쿼리 인터페이스" 참고
- 미완료: `matcher/run.py` 자동 판별 파이프라인은 아직 이 MCP 툴 안 씀 (기존 jsonb 통째 직렬화
  방식 유지 중) — LLM이 도구 호출로 실제로 능동 질의하게 엮는 건 다음 단계

### 부수 작업 — postgres pod CrashLoopBackOff 복구

이 작업 도중 공유 k8s postgres pod가 재시작 후 fsync 복구 중 readiness probe한테 계속
죽임당하는 무한 재시작 루프에 빠진 걸 발견. `startupProbe` 추가(최대 10분 유예)로 해결
(사용자가 직접 `kubectl patch` 실행, 제 샌드박스는 공유 리소스 변경이 막혀 있어서 명령만 안내함).

## 향후 계획 — LLM 판별 비동기화 (Redis)

현재 `pipeline.py`는 크롤링→LLM 판별까지 완전 동기 실행. 14b 모델 기준 판별 1건당 1~2분이라
공고×프로필 조합이 늘면 배치 전체 소요시간이 선형으로 늘어남 (POC 단계라 지금은 허용).

나중에 비동기 처리로 전환할 때 계획:

- 기존 k8s에 떠 있는 Redis(`default/redis`, ClusterIP `10.43.117.176:6379` — **ClusterIP라
  PG/MinIO와 달리 호스트에서 바로 접속 불가**, 구현 시점에 port-forward든 LoadBalancer
  전환이든 접근 경로 먼저 확보해야 함) 재사용
- 크롤링 단계는 그대로 동기 유지, "판별 대기 중인 (announcement, profile) 조합"을 Redis 큐에
  적재 → 워커 프로세스가 큐를 소비하며 LLM 호출 → 결과를 `matches` 테이블에 저장하는 구조로 분리
- **스키마(네임스페이스) 분리**: 다른 워크로드와 공유하는 Redis 인스턴스이므로, 이 프로젝트
  전용 key prefix(예: `gov_notice:*`) 또는 별도 Redis logical DB 번호(`SELECT 1` 등)로
  분리해서 간섭 없게 한다 — PG `gov_notice` 스키마, MinIO `gov-notice-raw` 버킷과 같은 원칙
- 지금은 설계만 기록, 실제 구현은 Phase 6 이후로 미룸 (YAGNI — 지금 배치 규모에서 비동기화
  이득보다 구현/운영 복잡도가 더 큼)

## 열린 결정 사항 (구현 착수 전 확인 필요)

1. ~~ollama 연동 방식~~ → 해결: 신규 compose 안 만듦, 호스트 Python 앱이 ollama(:11434)와
   postgres(:15432, k8s port-forward)에 각각 직접 접속하는 구조로 확정
2. **Ollama 모델 선택**: 로컬에 어떤 모델이 pull되어 있는지 확인 후 구조화 출력(JSON) 품질이
   괜찮은 모델로 확정
3. **fsc.go.kr 실제 HTML 구조**: 구현 착수 시 직접 분석 필요 (현재는 URL 패턴만 확보한 상태)
4. **알림 다이제스트 여부**: 공고가 한 번에 여러 건 쌓일 때 1건당 메시지 vs 묶음 메시지
