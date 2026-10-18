# gov-notice

공공기관 공고를 주기적으로 수집하고, **내 조건(나이·소득 등)에 맞는 공고만** 골라 Telegram으로 알려주는 개인용 자동화 봇.

## 왜 만들었나

지원금·정책 공고는 많은데 대부분 나와 상관없고, 자격 요건은 본문 깊숙이 숨어 있다.
매번 직접 읽고 "내가 해당되나?"를 판단하는 일을 LLM에게 맡긴다.

## 동작 원리

```
크롤러 ──▶ DB/오브젝트 저장 ──▶ LLM 판별 ──▶ Telegram 알림
(신규 공고만)  (원문 + 내 프로필)   (공고 × 프로필)   (적합 판정만)
```

1. **크롤링**: 기관별 플러그인 구조. 현재는 금융위원회 보도자료 1곳, 기관은 추가 가능.
2. **저장**: 공고 메타는 PostgreSQL, HTML 원문은 S3 호환 스토리지(MinIO/SeaweedFS). 원문을 보존해 두면 프롬프트가 바뀌어도 재판별할 수 있다.
3. **판별**: 로컬 Ollama LLM이 공고 본문과 내 프로필을 비교해 `적합 여부 / 확신도 / 사유`를 JSON으로 반환. 이미 판별한 조합은 건너뜀.
4. **알림**: 적합 판정된 공고만 Telegram 메시지로 발송.

프로필은 `profile_facts`(key-value + pgvector 임베딩)로도 저장되어, LLM이 MCP 툴로 "필요한 항목만" 의미 검색해서 조회할 수도 있다.

## 아키텍처

```
 host: python 파이프라인 (crawler → matcher → notifier)
     │            │               │
     ▼            ▼               ▼
 PostgreSQL    MinIO(S3)      Ollama(로컬 LLM)      Telegram Bot API
 (+pgvector)   원문 HTML

 k8s: 브라우저 ─▶ admin-web (nginx) ─▶ admin-api (FastAPI) ─▶ PostgreSQL
      (내 정보 CRUD, 공고 목록/상세, 판별 결과 확인)
```

## 기술 선택 이유

| 선택 | 이유 |
|---|---|
| 로컬 Ollama | API 비용·외부 의존 없음, 개인정보(소득 등)가 밖으로 나가지 않음 |
| PostgreSQL + pgvector | 정형 데이터와 임베딩 검색을 한 DB에서 처리 |
| 원문은 오브젝트 스토리지 | DB를 가볍게 유지, 원문 보존으로 재처리 가능 |
| 크롤러 플러그인 구조 | 새 기관 추가 시 구현체 하나만 등록 |
| 순수 HTML/JS 관리 페이지 | 소규모 개인 도구라 프레임워크 불필요 |

## 실행

```bash
cp .env.example .env      # DB, MinIO, Ollama, Telegram 값 채우기
uv sync
uv run alembic upgrade head
uv run python -m gov_notice.pipeline   # 크롤링 → 판별 → 알림
```

Telegram 봇 준비는 [docs/telegram-bot-setup.md](docs/telegram-bot-setup.md), 상세 설계는 [docs/](docs/) 참고.
