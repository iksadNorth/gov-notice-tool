"""merge user_profiles into profile_facts

user_profiles(원본 jsonb)와 profile_facts(검색용 파생 테이블)로 쪼개져 있던 걸
profile_facts 하나로 합침. matches도 user_profile_id(FK) 대신 profile_label(문자열) 사용.
데이터 변환이 필요해서 autogenerate 대신 수동으로 작성함.

Revision ID: e597fe94997d
Revises: e5e329fd908c
Create Date: 2026-10-09
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e597fe94997d"
down_revision: Union[str, Sequence[str], None] = "e5e329fd908c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # profile_facts: profile_label/is_active 컬럼 추가하고 user_profiles에서 값 채워넣기
    op.execute("ALTER TABLE profile_facts ADD COLUMN profile_label VARCHAR")
    op.execute("ALTER TABLE profile_facts ADD COLUMN is_active BOOLEAN")
    op.execute(
        """
        UPDATE profile_facts
        SET profile_label = up.label, is_active = up.is_active
        FROM user_profiles up
        WHERE up.id = profile_facts.user_profile_id
        """
    )
    op.execute("ALTER TABLE profile_facts ALTER COLUMN profile_label SET NOT NULL")
    op.execute("ALTER TABLE profile_facts ALTER COLUMN is_active SET NOT NULL")
    op.execute(
        "ALTER TABLE profile_facts DROP CONSTRAINT profile_facts_user_profile_id_fkey"
    )
    op.execute(
        "ALTER TABLE profile_facts DROP CONSTRAINT profile_facts_user_profile_id_key_key"
    )
    op.execute("ALTER TABLE profile_facts DROP COLUMN user_profile_id")
    op.execute(
        "ALTER TABLE profile_facts ADD CONSTRAINT profile_facts_profile_label_key_key "
        "UNIQUE (profile_label, key)"
    )

    # matches: profile_label 컬럼 추가하고 채워넣기
    op.execute("ALTER TABLE matches ADD COLUMN profile_label VARCHAR")
    op.execute(
        """
        UPDATE matches
        SET profile_label = up.label
        FROM user_profiles up
        WHERE up.id = matches.user_profile_id
        """
    )
    op.execute("ALTER TABLE matches ALTER COLUMN profile_label SET NOT NULL")
    op.execute("ALTER TABLE matches DROP CONSTRAINT matches_user_profile_id_fkey")
    op.execute(
        "ALTER TABLE matches DROP CONSTRAINT matches_announcement_id_user_profile_id_key"
    )
    op.execute("ALTER TABLE matches DROP COLUMN user_profile_id")
    op.execute(
        "ALTER TABLE matches ADD CONSTRAINT matches_announcement_id_profile_label_key "
        "UNIQUE (announcement_id, profile_label)"
    )

    op.execute("DROP TABLE user_profiles")


def downgrade() -> None:
    # 거의 안 쓸 거라 최소한만 — user_profiles 재생성 + 역변환
    op.execute(
        """
        CREATE TABLE user_profiles (
            id SERIAL PRIMARY KEY,
            label VARCHAR NOT NULL,
            data JSONB NOT NULL,
            is_active BOOLEAN NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        INSERT INTO user_profiles (label, data, is_active)
        SELECT profile_label, jsonb_object_agg(key, value_text), bool_or(is_active)
        FROM profile_facts
        GROUP BY profile_label
        """
    )

    op.execute("ALTER TABLE profile_facts ADD COLUMN user_profile_id INTEGER")
    op.execute(
        """
        UPDATE profile_facts
        SET user_profile_id = up.id
        FROM user_profiles up
        WHERE up.label = profile_facts.profile_label
        """
    )
    op.execute("ALTER TABLE profile_facts ALTER COLUMN user_profile_id SET NOT NULL")
    op.execute(
        "ALTER TABLE profile_facts ADD CONSTRAINT profile_facts_user_profile_id_fkey "
        "FOREIGN KEY (user_profile_id) REFERENCES user_profiles(id)"
    )
    op.execute(
        "ALTER TABLE profile_facts DROP CONSTRAINT profile_facts_profile_label_key_key"
    )
    op.execute(
        "ALTER TABLE profile_facts ADD CONSTRAINT profile_facts_user_profile_id_key_key "
        "UNIQUE (user_profile_id, key)"
    )
    op.execute("ALTER TABLE profile_facts DROP COLUMN profile_label")
    op.execute("ALTER TABLE profile_facts DROP COLUMN is_active")

    op.execute("ALTER TABLE matches ADD COLUMN user_profile_id INTEGER")
    op.execute(
        """
        UPDATE matches
        SET user_profile_id = up.id
        FROM user_profiles up
        WHERE up.label = matches.profile_label
        """
    )
    op.execute("ALTER TABLE matches ALTER COLUMN user_profile_id SET NOT NULL")
    op.execute(
        "ALTER TABLE matches ADD CONSTRAINT matches_user_profile_id_fkey "
        "FOREIGN KEY (user_profile_id) REFERENCES user_profiles(id)"
    )
    op.execute(
        "ALTER TABLE matches DROP CONSTRAINT matches_announcement_id_profile_label_key"
    )
    op.execute(
        "ALTER TABLE matches ADD CONSTRAINT matches_announcement_id_user_profile_id_key "
        "UNIQUE (announcement_id, user_profile_id)"
    )
    op.execute("ALTER TABLE matches DROP COLUMN profile_label")
