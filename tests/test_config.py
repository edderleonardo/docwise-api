"""DATABASE_URL normalization: accept provider strings as-is."""

import pytest

from app.config import Settings

NEON_RAW = (
    "postgresql://user:pass@ep-x-pooler.c-3.us-east-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def make_settings(url: str) -> Settings:
    # _env_file=None: ignore the developer's .env so only `url` is under test
    return Settings(database_url=url, _env_file=None)


class TestDatabaseUrlNormalization:
    def test_neon_string_is_fully_normalized(self):
        s = make_settings(NEON_RAW)
        assert s.database_url == (
            "postgresql+asyncpg://user:pass@ep-x-pooler.c-3.us-east-2.aws.neon.tech/neondb"
        )

    def test_asyncpg_url_passes_through_untouched(self):
        url = "postgresql+asyncpg://u:p@localhost:5432/docwise"
        assert make_settings(url).database_url == url

    def test_strips_only_incompatible_params(self):
        s = make_settings(
            "postgresql://u:p@host/db?sslmode=require&application_name=docwise"
        )
        assert s.database_url == (
            "postgresql+asyncpg://u:p@host/db?application_name=docwise"
        )

    def test_surrounding_whitespace_is_removed(self):
        s = make_settings("  postgresql+asyncpg://u:p@host/db\n")
        assert s.database_url == "postgresql+asyncpg://u:p@host/db"

    def test_garbage_still_fails_loudly(self):
        with pytest.raises(Exception):
            make_settings("not-a-url").database_url
