import requests

from gov_notice.config import settings

EMBED_MODEL = "nomic-embed-text"


def embed_text(text: str) -> list[float]:
    """프로필 키("월급")와 쿼리("월급") 양쪽 다 이 함수로 대칭 임베딩.

    search_query:/search_document:는 질문→긴 문서 비대칭 검색(RAG)용 프리픽스라
    명사-명사 키워드 매칭엔 안 맞음 — nomic-embed-text의 clustering: 프리픽스가
    "비슷한 짧은 텍스트를 같은 그룹으로 묶는" 대칭 용도라 이 경우에 더 맞는다.
    """
    resp = requests.post(
        f"{settings.ollama_host}/api/embed",
        json={"model": EMBED_MODEL, "input": f"clustering: {text}"},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["embeddings"][0]
