# LLM 판별 로직

## 사용 모델

- Ollama 컨테이너(localhost:11434)를 통해 로컬 모델 호출
- 모델명은 설정값으로 분리 (`.env`의 `OLLAMA_MODEL`), 추후 교체/비교 용이하게
- 구조화 출력이 필요하므로 JSON 모드/함수 호출을 지원하는 모델 권장 (예: qwen2.5, llama3.1 계열 등 —
  실제 모델은 구현 착수 시점에 로컬에 받아져 있는 것 확인 후 확정)

## 입력

1. 공고 정보: 제목, 본문 텍스트(`announcements.content_text`)
2. 사용자 프로필: `user_profiles.data`(jsonb) 전체를 그대로 직렬화해 프롬프트에 주입 (POC 범위,
   아래 "향후 계획" 참고)

## 구현 현황 (완료)

- `matcher/prompt.py` — system 프롬프트 + `build_user_prompt()` + `RESPONSE_SCHEMA`
- `matcher/ollama_client.py` — `ollama.chat(format=RESPONSE_SCHEMA)`로 구조화 출력 강제,
  `JudgeResult(is_eligible, confidence, reason)` 반환
- `matcher/run.py` — announcement × active profile 조합 순회, 이미 판별된 조합 스킵,
  `ON CONFLICT DO NOTHING`으로 저장. `pipeline.run_pipeline()`에서 크롤링 뒤에 연결됨
- 적합/부적합/자격요건 불명확 세 케이스 실제 ollama(`qwen2.5:14b-instruct`) 호출로 검증 완료

## 프로필 능동 쿼리 인터페이스 (MCP + 벡터 검색) — 구현 완료

앞서 "향후 계획"으로만 적어뒀던 것을 실제로 구현함. `user_profiles.data`(jsonb)를
자동 판별(`matcher/run.py`)에는 여전히 통째로 직렬화해서 넘기지만(POC 경로는 그대로 둠),
별도로 LLM이 **필요한 키만 자연어로 능동 조회**할 수 있는 MCP 툴을 추가로 만들었다.

### 구조

- 처음엔 pgvector 확장이 이 postgres 이미지에 없어서(`pg_available_extensions`에 없음)
  PG float[] + Python 코사인 유사도로 구현했었음. 이후 공유 postgres 이미지
  (`/home/iksadnorth/project/realestimate/docker/postgres`)에 pgvector를 실제로 추가함
  (`apt-extensions.txt`에 `postgresql-16-pgvector` 추가 → 이미지 재빌드 → k3s import →
  `airflow` DB에 `CREATE EXTENSION vector` 적용 완료, 덤으로 `pg_stat_statements`도 설치함).
  → 이후 실제로 pgvector 전환 완료: `profile_facts.embedding`을 `Vector(768)` 타입으로 바꾸고
  `<=>`(코사인 거리) 연산자로 DB 레벨 정렬. Python 쪽 코사인 계산 루프는 삭제함.
  - `gov_notice.profile_facts` 테이블(`key`, `value_text`, `embedding vector(768)`)에
    `user_profiles.data`를 key-value로 풀어서 저장
  - **주의**: `vector` 타입/연산자가 `public` 스키마에 있어서, `db/session.py`의
    search_path를 `gov_notice`만 두면 "operator does not exist" 에러남 →
    `search_path=gov_notice,public`으로 수정함
  - 쿼리 바인딩도 주의 필요: SQLAlchemy에 벡터를 그냥 list로 넘기면 타입 추론이 안 돼서
    `<=> unknown` 에러남 → `literal(vec, type_=Vector(768))`로 명시적 캐스팅해야 함

### 쿼리/저장 방식 — 비대칭 → 대칭으로 수정

초기 구현은 두 가지가 어긋나 있었음:
1. MCP `query` 파라미터를 자연어 문장으로 받게 열어뒀는데, 저장된 키는 명사형 라벨이라
   문장 임베딩과 명사 임베딩이 애초에 다른 의미 공간에 놓임
2. `search_query:`/`search_document:` 프리픽스는 "질문→긴 문서" 비대칭 검색(RAG)용인데,
   명사-명사 키워드 매칭에 그 프리픽스를 쓴 것 자체가 용도에 안 맞았음

수정:
- `query`는 명사/키워드 1~3개로 제한 (MCP 툴 docstring에 명시)
- 임베딩을 대칭 방식(`embed_text()` 하나, `clustering:` 프리픽스)으로 통일 —
  nomic-embed-text에서 "비슷한 짧은 텍스트를 같은 그룹으로 묶는" 용도의 프리픽스라
  명사-명사 매칭에 더 맞음
- 추가로 `user_profiles.data`의 key 자체를 **영문 변수명 → 한글**로 전환
  (`birth_date` → `생년월일`, `monthly_income` → `월급` 등). 이걸로 `KEY_LABELS` 번역
  매핑 레이어가 통째로 불필요해짐 (삭제함) — 쿼리와 저장이 같은 언어라 의미 공간이 안 어긋남

결과: 테스트 쿼리 5개 중 4개가 top-1 정확 매칭(이전엔 변별력 자체가 약해서 점수가 전부
0.6~0.7대에 뭉쳐 있었는데, 지금은 동일어 1.0 / 의미상 유사 0.9대 / 그 외 낮은 점수로
분리가 뚜렷해짐). 1건("소득"→생년월일 1위, 월급이 2위)은 여전히 틀림 — 임베딩 모델
한계로 완벽친 않음, 필요시 top_k를 넉넉히 주거나 다국어 임베딩 모델 교체 고려
- 임베딩 모델: ollama `nomic-embed-text`(768차원) 신규 pull
  - **주의**: 이 모델은 `search_query: `/`search_document: ` 프리픽스를 안 붙이면 변별력이
    크게 떨어짐(실제로 처음엔 "월급"이 "거주지역"보다 유사도 높게 나오는 오판정 있었음).
    `embeddings.py`에서 쿼리/문서 각각 프리픽스 붙여서 호출
  - 다국어(특히 한글) 성능이 약함 — top-1 정확도는 보통이고 top-3까지 넓히면 대부분 커버됨.
    정확도 더 필요해지면 다국어 임베딩 모델(예: bge-m3)로 교체 고려
  - 영문 key와 한글 쿼리 사이 의미 간극을 메우려고 `embeddings.py`의 `KEY_LABELS`에
    필드별 한글 동의어/유사 질문 라벨을 수작업으로 붙여서 임베딩
- `matcher/profile_store.py` — `sync_profile_facts()`(upsert, `(user_profile_id, key)` 멱등),
  `query_profile_facts()`(쿼리 임베딩 후 Python에서 top_k 유사도 검색)
- `matcher/mcp_server.py` — `mcp` SDK(v2, `MCPServer`)로 `query_profile(query, profile_label,
  top_k)` 툴 하나 노출. stdio로 구동(`uv run python -m gov_notice.matcher.mcp_server`)

### 설계 의도

프로필 정보량이 방대해져도(가족 구성원별, 수십 개 속성 등) 매 호출마다 전체를 컨텍스트에
욱여넣지 않고, 필요한 것만 그때그때 꺼내 쓰는 구조. `user_profiles.data`를 jsonb 하나로
고정 컬럼 없이 설계해둔 게 이 전환을 가능하게 함 — 새 필드 추가돼도 `sync_profile_facts`가
알아서 다 풀어서 임베딩함.

### 아직 안 한 것

- `matcher/run.py`(자동 판별 파이프라인)는 아직 이 MCP 툴을 안 씀 — 여전히 `profile.data`
  통째로 프롬프트에 넣는 기존 방식. MCP 툴은 지금은 독립된 인터페이스로만 존재
  (LLM이 도구 호출로 능동 질의하는 플로우에 실제로 연결하는 건 다음 단계)
- 벡터 검색 대상이 `profile_facts` 하나뿐 — 공고 본문 등 다른 데이터로 확장 여부는 미정

## 출력 (구조화 JSON)

```json
{
  "is_eligible": true,
  "confidence": 0.82,
  "reason": "만 19~34세 청년을 대상으로 하며 소득분위 8분위 이하 조건을 충족함"
}
```

- `is_eligible`: boolean — 지원 자격 충족 여부
- `confidence`: 0~1 — LLM 자체 확신도 (낮으면 애매한 공고로 간주, 알림 여부 정책에 활용 가능)
- `reason`: 사람이 읽을 수 있는 한 줄 판단 근거 (Telegram 메시지에도 포함)

## 프롬프트 설계 원칙

- **System 프롬프트**: "당신은 공공기관 지원 공고와 개인 정보를 비교해 지원 자격 여부를
  판별하는 어시스턴트다. 반드시 JSON으로만 답하라" 등 역할/출력 형식 고정
- **공고 본문이 긴 경우**: 토큰 제한을 고려해 본문을 일정 길이로 자르거나, 1차로 공고 유형/자격
  요건 문단만 추출하는 전처리 단계를 둘 수 있음 (1차 구현 범위에서는 단순 truncate로 시작)
- **모호한 조건 처리**: 공고에 자격 요건이 명시되지 않은 경우 `is_eligible=false`,
  `confidence` 낮게, reason에 "자격 요건 불명확"으로 표기하도록 유도

## 처리 정책

- `confidence`가 임계값(예: 0.5) 미만이면 Telegram 알림을 보내지 않고 `matches`에만 기록
  (오탐으로 인한 알림 피로 방지) — 임계값은 설정값으로 분리
- 동일 (공고, 프로필) 조합은 1회만 판별 (`matches` UNIQUE 제약으로 보장)
- LLM 호출 실패/timeout 시 재시도 1회 후 실패 기록, 다음 배치에서 재시도 대상으로 남김
  (즉, 실패 시 `matches` row를 만들지 않고 미판별 상태 유지)

## 비용/성능 고려

- 로컬 LLM이므로 API 비용은 없으나, 공고 수 × 프로필 수만큼 호출이 발생함
  → 1차 범위(프로필 1개, 기관 1곳)에서는 문제 없으나, 기관이 늘어나면 배치 처리/캐싱 전략 재검토 필요
