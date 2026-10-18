"""관리용 웹 API. CRUD/목록/상세 전부 이 파일 하나에 몰아넣음 — 소규모 관리자용 도구라
라우터 분리, 서비스 레이어 분리 같은 추상화 없이 핸들러에서 바로 DB 접근.
"""

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, func

from gov_notice.db.models import Agency, Announcement, Match
from gov_notice.db.session import SessionLocal
from gov_notice.matcher.profile_store import (
    delete_profile,
    get_profile,
    list_profile_labels,
    upsert_profile,
)
from gov_notice.notifier.telegram import build_message

app = FastAPI(title="gov-notice admin api")


class ProfileIn(BaseModel):
    label: str
    data: dict
    is_active: bool = True


@app.get("/api/profiles")
def list_profiles():
    with SessionLocal() as db:
        labels = list_profile_labels(db)
        # 가드: 프로필이 하나도 없으면 빈 배열
        return [get_profile(db, label) for label in labels]


@app.post("/api/profiles")
def create_profile(body: ProfileIn):
    # 가드: label이 비어있으면 저장 자체를 거부 — 빈 label은 URL로 삭제가 안 돼서 고아 row가 됨
    if not body.label.strip():
        raise HTTPException(400, "label은 빈 문자열일 수 없습니다")

    with SessionLocal() as db:
        # 가드: 이미 있는 label이면 그냥 덮어쓰기 — 별도 중복 체크 분기 안 둠
        upsert_profile(db, body.label, body.data, body.is_active)
        return get_profile(db, body.label)


@app.put("/api/profiles/{label}")
def update_profile(label: str, body: ProfileIn):
    # 가드: 같은 이유로 빈 label로 바꾸는 것도 거부
    if not body.label.strip():
        raise HTTPException(400, "label은 빈 문자열일 수 없습니다")

    with SessionLocal() as db:
        existing = get_profile(db, label)
        # 가드: 없는 프로필이면 바로 404
        if existing is None:
            raise HTTPException(404, "profile not found")

        # label 자체를 바꾸는 경우: 새 label로 새로 만들고 기존 걸 지움
        if body.label != label:
            upsert_profile(db, body.label, body.data, body.is_active)
            delete_profile(db, label)
            return get_profile(db, body.label)

        upsert_profile(db, label, body.data, body.is_active)
        return get_profile(db, label)


@app.delete("/api/profiles/{label}")
def delete_profile_route(label: str):
    with SessionLocal() as db:
        existing = get_profile(db, label)
        if existing is None:
            raise HTTPException(404, "profile not found")

        delete_profile(db, label)
        return {"ok": True}


@app.get("/api/announcements")
def list_announcements(
    page: int = 1,
    page_size: int = 20,
    is_eligible: bool | None = None,
    agency: str | None = None,
    title: str | None = None,
):
    # 가드: 이상한 값 들어오면 기본값으로 눌러버림
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 20

    with SessionLocal() as db:
        # 지금은 프로필이 1개뿐이라 공고당 매치도 최대 1개 — outer join해도 row가 안 늘어남.
        # 프로필 여러 개로 늘어나면 공고당 여러 row 나올 수 있으니 그때 다시 봐야 함.
        query = (
            select(Announcement, Agency, Match.is_eligible)
            .join(Agency, Announcement.agency_id == Agency.id)
            .outerjoin(Match, Match.announcement_id == Announcement.id)
        )

        # 검색 필터 — 값 없으면 조건 안 붙임
        if is_eligible is not None:
            query = query.where(Match.is_eligible == is_eligible)
        if agency:
            query = query.where(Agency.name.ilike(f"%{agency}%"))
        if title:
            query = query.where(Announcement.title.ilike(f"%{title}%"))

        total = db.scalar(select(func.count()).select_from(query.subquery()))

        rows = db.execute(
            query.order_by(Announcement.published_at.desc().nullslast(), Announcement.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()

        items = [
            {
                "id": ann.id,
                "agency_name": agency_row.name,
                "title": ann.title,
                "published_at": ann.published_at.date().isoformat() if ann.published_at else None,
                "source_url": ann.source_url,
                "is_eligible": eligible,
            }
            for ann, agency_row, eligible in rows
        ]
        return {"items": items, "total": total, "page": page, "page_size": page_size}


@app.get("/api/announcements/{announcement_id}")
def get_announcement(announcement_id: int):
    with SessionLocal() as db:
        row = db.execute(
            select(Announcement, Agency)
            .join(Agency, Announcement.agency_id == Agency.id)
            .where(Announcement.id == announcement_id)
        ).first()

        # 가드: 없는 공고면 바로 404
        if row is None:
            raise HTTPException(404, "announcement not found")

        ann, agency = row

        match_rows = db.scalars(
            select(Match)
            .where(Match.announcement_id == announcement_id)
            .order_by(Match.judged_at.desc())
        ).all()

        matches = [
            {
                "profile_label": m.profile_label,
                "is_eligible": m.is_eligible,
                "confidence": float(m.confidence) if m.confidence is not None else None,
                "reason": m.reason,
                "missing_info": m.missing_info,
                "model_name": m.model_name,
                "judged_at": m.judged_at.isoformat() if m.judged_at else None,
                "notified_at": m.notified_at.isoformat() if m.notified_at else None,
                "trace_key": m.trace_key,
                # 실제 알림 발송 로직(notifier/telegram.py)과 똑같은 포맷으로 미리보기 생성
                "telegram_preview": build_message(
                    agency.name,
                    ann.title,
                    ann.published_at.date().isoformat() if ann.published_at else None,
                    m.reason,
                    ann.source_url,
                    is_eligible=m.is_eligible,
                    missing_info=m.missing_info,
                ),
            }
            for m in match_rows
        ]

        return {
            "id": ann.id,
            "agency_name": agency.name,
            "title": ann.title,
            "content_text": ann.content_text,
            "published_at": ann.published_at.date().isoformat() if ann.published_at else None,
            "source_url": ann.source_url,
            "matches": matches,
        }
