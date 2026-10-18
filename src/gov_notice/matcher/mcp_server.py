"""프로필 정보를 능동 쿼리로 제공하는 MCP 서버.

LLM이 명사/키워드로 호출하면, profile_facts에서 벡터 유사도(pgvector)로 가장 가까운
key-value를 찾아 반환한다. 프로필 전체를 매번 컨텍스트에 안 넣고 필요한 것만 꺼내
쓰는 인터페이스 (docs/04-llm-matching.md 참고).

쿼리는 반드시 명사/키워드 1~3개로 (예: "월급", "거주지역") — 완전한 문장("월급이 얼마인지
알려줘")으로 주면 저장된 키(명사형 라벨)와 의미 공간이 어긋나 정확도가 떨어진다.
쿼리/저장 양쪽 다 같은 방식(symmetric, clustering: 프리픽스)으로 임베딩하기 때문에
문장 대 명사 비교는 애초에 설계 범위 밖이다.

실행: uv run python -m gov_notice.matcher.mcp_server
"""

from mcp.server.mcpserver import MCPServer

from gov_notice.db.session import SessionLocal
from gov_notice.matcher.profile_store import query_profile_facts

mcp = MCPServer("gov-notice-profile")


@mcp.tool()
def query_profile(query: str, profile_label: str = "본인", top_k: int = 3) -> list[dict]:
    """사용자 프로필에서 쿼리 명사/키워드와 가장 가까운 key-value 정보를 top_k개 반환한다.

    query는 명사/키워드만 (예: "월급", "나이"). 문장으로 주지 말 것 — 저장된 키가
    전부 명사형이라 문장을 넣으면 의미 공간이 어긋나 정확도가 떨어진다.

    예: query="월급" -> [{"key": "월급", "value": "2800000", "score": 1.0}, ...]
    """
    with SessionLocal() as session:
        results = query_profile_facts(session, profile_label, query, top_k=top_k)
        return [{"key": r.key, "value": r.value, "score": round(r.score, 3)} for r in results]


if __name__ == "__main__":
    mcp.run()
