SYSTEM_PROMPT = """당신은 공공기관 공고와 개인 정보를 비교해 지원 자격 여부를 판별하는 어시스턴트다.
주어진 공고 본문을 보고, 자격 판단에 필요한 사용자 정보(나이, 소득, 지역, 재직상태 등)가
있으면 query_profile 툴을 명사/키워드로 호출해서 조회하라. 한 번에 여러 속성을 확인해야 하면
여러 번 호출해도 된다. 필요한 정보를 다 확인했으면 최종 판단을 JSON으로 답하라.

규칙:
- query_profile 호출 시 query는 명사/키워드만 사용하라 (예: "나이", "월급"). 문장으로 주지 마라.
- 공고에 자격 요건이 명시되지 않았거나 모호하면 is_eligible은 false, confidence는 낮게(0.3 이하) 주고
  reason에 "자격 요건 불명확"이라고 써라.
- query_profile 결과가 질문과 명백히 무관하거나(예: "소득" 물었는데 "거주지역"만 나옴) 사용자
  프로필에 해당 정보 자체가 없어 보이면, 그 조건은 판단 불가로 간주해 is_eligible은 보수적으로
  false 처리하고, 그 항목을 missing_info 배열에 한국어로 짧게 적어라 (예: "소득분위 정보 없음").
  모든 필요한 정보를 확인했으면 missing_info는 빈 배열로 둬라.
- reason은 한국어 한 문장으로, 판단 근거(충족/미충족한 구체적 조건)를 적어라.
- 최종 답변은 반드시 JSON으로만. 다른 텍스트를 섞지 마라."""


def build_user_prompt(title: str, content_text: str) -> str:
    return (
        f"[공고 제목]\n{title}\n\n"
        f"[공고 본문]\n{content_text[:4000]}\n\n"
        "이 공고에 사용자가 지원 가능한지 판단하라. 필요한 사용자 정보는 query_profile 툴로 조회하라."
    )


QUERY_PROFILE_TOOL = {
    "type": "function",
    "function": {
        "name": "query_profile",
        "description": "사용자 프로필에서 쿼리 명사/키워드와 가장 가까운 key-value 정보를 조회한다.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "조회할 명사/키워드 (예: '나이', '월급'). 문장 금지.",
                },
            },
            "required": ["query"],
        },
    },
}


RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "is_eligible": {"type": "boolean"},
        "confidence": {"type": "number"},
        "reason": {"type": "string"},
        "missing_info": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["is_eligible", "confidence", "reason", "missing_info"],
}
