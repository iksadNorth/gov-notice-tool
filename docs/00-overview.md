# 프로젝트 개요: 공공기관 공고 맞춤 알림 봇

## 목표
공공기관(정부부처, 지자체, 산하기관 등)이 올리는 보도자료/공고를 주기적으로 수집하고,
사용자의 개인 정보(나이, 소득분위, 월급 등)를 바탕으로 LLM이 "내가 지원 가능한 공고인지"를
판별하여, 해당하는 공고만 Telegram으로 알림을 보내는 개인용 자동화 시스템.

## 파이프라인 (4단계)

```
[1] 크롤러          [2] DB 저장              [3] LLM 판별            [4] 알림
공공기관 보도자료  →  공고 원문 + 사용자  →  로컬 ollama LLM이    →  적합 판정된
사이트를 주기적으로   프로필을 DB에 저장       공고-프로필 매칭 평가     공고만 Telegram
크롤링해 신규 공고                             (적합/부적합 + 사유)     메시지로 발송
만 수집
```

## 핵심 설계 원칙

1. **확장성 있는 크롤러**: 시작은 금융위원회(fsc.go.kr) 보도자료 게시판 1곳이지만,
   향후 기관이 계속 추가될 것을 전제로 "사이트별 크롤러 플러그인" 구조로 설계한다.
   (상세: [02-crawler.md](./02-crawler.md))
2. **원문 보존 + 구조화 분리**: 크롤링한 원문(HTML/텍스트)과 LLM이 뽑아낸 구조화 정보를
   분리 저장하여, 파싱 로직이나 LLM 프롬프트가 바뀌어도 재처리가 가능하게 한다.
3. **로컬 LLM 활용**: 이미 떠 있는 Ollama 컨테이너(localhost:11434)를 통해 판별을 수행하며,
   외부 API 비용/네트워크 의존 없이 동작한다.
4. **정기 배치 실행**: cron/스케줄러로 하루 1~2회 전체 파이프라인(크롤링 → 판별 → 알림)을
   자동 실행한다.

## 기술 스택 (확정)

| 영역 | 선택 |
|---|---|
| 언어 | Python |
| DB | PostgreSQL (k8s 기존 postgres pod, LoadBalancer 192.168.0.52:5432 직결, 전용 스키마 `gov_notice` 격리) |
| 원문 저장소 | S3 호환 오브젝트 스토리지 (k8s, 192.168.0.57:9000, S3 API 호환) — HTML 원문은 PG 밖으로 분리. 서비스명/클라이언트는 `minio`이지만 실제 서버는 SeaweedFS (2026-10 MinIO 이미지 배포 중단으로 교체, [06-roadmap.md](./06-roadmap.md) 참고) |
| LLM | Ollama (이미 기동 중, localhost:11434) |
| 크롤링 | requests + BeautifulSoup (필요 시 Playwright 보강) |
| 알림 | Telegram Bot API |
| 실행 방식 | 정기 배치 (cron 또는 APScheduler) |

## 문서 구성

- [00-overview.md](./00-overview.md) — 이 문서. 전체 개요
- [01-architecture.md](./01-architecture.md) — 시스템 구조, 디렉토리 구조, docker-compose 설계
- [02-crawler.md](./02-crawler.md) — 크롤러 확장 구조, 사이트별 플러그인 설계
- [03-database-schema.md](./03-database-schema.md) — PostgreSQL 스키마 설계
- [04-llm-matching.md](./04-llm-matching.md) — LLM 판별 로직, 프롬프트 설계
- [05-telegram-notification.md](./05-telegram-notification.md) — 알림 포맷, 발송 로직
- [06-roadmap.md](./06-roadmap.md) — 개발 단계별 로드맵, 열린 결정 사항

## 현재 확정된 결정 사항

- 크롤링 1호 대상: 금융위원회(fsc.go.kr) 보도자료 게시판 (`/no010101/...`)
  → 이후 타 기관으로 확장 예정, 크롤러는 처음부터 다중 기관 지원 구조로 설계
- 언어/프레임워크: Python
- DB: PostgreSQL (k8s 기존 postgres pod, LoadBalancer 192.168.0.52:5432 직결, 전용 스키마 `gov_notice`로 격리해 필요 시 통째로 drop 가능하게)
- 실행 방식: 정기 배치(cron/스케줄러)로 전체 파이프라인 자동 실행
