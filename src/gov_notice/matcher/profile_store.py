from dataclasses import dataclass

from pgvector.sqlalchemy import Vector
from sqlalchemy import literal, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from gov_notice.db.models import EMBEDDING_DIM, Match, ProfileFact
from gov_notice.matcher.embeddings import embed_text


def list_profile_labels(session: Session, active_only: bool = False) -> list[str]:
    query = select(ProfileFact.profile_label).distinct()
    if active_only:
        query = query.where(ProfileFact.is_active.is_(True))
    return list(session.scalars(query).all())


def get_profile(session: Session, profile_label: str) -> dict | None:
    facts = session.scalars(
        select(ProfileFact).where(ProfileFact.profile_label == profile_label)
    ).all()
    # 가드: 이 label로 된 fact가 하나도 없으면 존재하지 않는 프로필
    if not facts:
        return None

    return {
        "label": profile_label,
        "is_active": facts[0].is_active,
        "data": {f.key: f.value_text for f in facts},
    }


def upsert_profile(session: Session, profile_label: str, data: dict, is_active: bool) -> None:
    """data의 key들을 전부 upsert하고, data에 없는 기존 key는 삭제 (덮어쓰기 동기화)."""
    existing_keys = set(
        session.scalars(
            select(ProfileFact.key).where(ProfileFact.profile_label == profile_label)
        ).all()
    )
    removed_keys = existing_keys - set(data.keys())
    for key in removed_keys:
        session.query(ProfileFact).filter(
            ProfileFact.profile_label == profile_label, ProfileFact.key == key
        ).delete()

    for key, value in data.items():
        value_text = str(value)
        vec = embed_text(key)
        stmt = (
            insert(ProfileFact)
            .values(
                profile_label=profile_label,
                key=key,
                value_text=value_text,
                embedding=vec,
                is_active=is_active,
            )
            .on_conflict_do_update(
                index_elements=[ProfileFact.profile_label, ProfileFact.key],
                set_={"value_text": value_text, "embedding": vec, "is_active": is_active},
            )
        )
        session.execute(stmt)
    session.commit()


def delete_profile(session: Session, profile_label: str) -> None:
    # 이 프로필을 참조하는 matches도 같이 지움 (FK는 없지만 논리적으로 묶여있어서)
    session.query(Match).filter(Match.profile_label == profile_label).delete()
    session.query(ProfileFact).filter(ProfileFact.profile_label == profile_label).delete()
    session.commit()


@dataclass
class FactMatch:
    key: str
    value: str
    score: float


def query_profile_facts(
    session: Session, profile_label: str, query: str, top_k: int = 3
) -> list[FactMatch]:
    """명사/키워드 쿼리로 가장 유사한 프로필 키-값 top_k개 반환.

    pgvector `<=>`(코사인 거리) 연산자로 DB 레벨에서 정렬 — Python 루프 계산 없음.
    score = 1 - cosine_distance (1에 가까울수록 유사).
    """
    query_vec = literal(embed_text(query), type_=Vector(EMBEDDING_DIM))
    distance = ProfileFact.embedding.cosine_distance(query_vec)
    rows = session.execute(
        select(ProfileFact.key, ProfileFact.value_text, distance.label("distance"))
        .where(ProfileFact.profile_label == profile_label)
        .order_by(distance)
        .limit(top_k)
    ).all()
    return [FactMatch(key=key, value=value_text, score=1 - dist) for key, value_text, dist in rows]
