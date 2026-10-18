import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    MetaData,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

EMBEDDING_DIM = 768

metadata = MetaData()


class Base(DeclarativeBase):
    metadata = metadata


class Agency(Base):
    __tablename__ = "agencies"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    base_url: Mapped[str] = mapped_column(String)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_crawled_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    announcements: Mapped[list["Announcement"]] = relationship(back_populates="agency")


class Announcement(Base):
    __tablename__ = "announcements"
    __table_args__ = (UniqueConstraint("agency_id", "source_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    agency_id: Mapped[int] = mapped_column(ForeignKey("agencies.id"))
    source_url: Mapped[str] = mapped_column(String)
    title: Mapped[str] = mapped_column(String)
    content_text: Mapped[str] = mapped_column(Text)
    content_html_key: Mapped[str | None] = mapped_column(String, nullable=True)
    published_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    crawled_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    agency: Mapped["Agency"] = relationship(back_populates="announcements")
    matches: Mapped[list["Match"]] = relationship(back_populates="announcement")


class ProfileFact(Base):
    """프로필 정보를 key-value 한 줄씩 + 임베딩(pgvector)으로 저장하는 단일 테이블.

    원래는 user_profiles(원본 jsonb)와 profile_facts(검색용 파생 테이블)로 나뉘어 있었는데,
    데이터가 두 군데로 쪼개져 있는 게 혼란스럽다고 해서 이거 하나로 합침.
    profile_label(문자열)이 "프로필 이름" 역할을 함 — 같은 label을 가진 행들이 한 프로필.
    key는 영문 변수명이 아니라 한글로 저장(예: "월급") — 쿼리도 한글이라 번역 매핑 계층 불필요.
    """

    __tablename__ = "profile_facts"
    __table_args__ = (UniqueConstraint("profile_label", "key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_label: Mapped[str] = mapped_column(String)
    key: Mapped[str] = mapped_column(String)
    value_text: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIM))
    # 같은 profile_label의 모든 행에 똑같은 값이 중복 저장됨 — 프로필 단위 플래그라 어쩔 수 없음
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Match(Base):
    __tablename__ = "matches"
    __table_args__ = (UniqueConstraint("announcement_id", "profile_label"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"))
    profile_label: Mapped[str] = mapped_column(String)
    is_eligible: Mapped[bool] = mapped_column(Boolean)
    confidence: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    reason: Mapped[str] = mapped_column(Text)
    missing_info: Mapped[list[str]] = mapped_column(JSONB, default=list)
    trace_key: Mapped[str | None] = mapped_column(String, nullable=True)
    model_name: Mapped[str] = mapped_column(String)
    judged_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    notified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    announcement: Mapped["Announcement"] = relationship(back_populates="matches")
