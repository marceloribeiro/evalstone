import pytest
from alembic.config import Config

from app.config import Settings


def test_alembic_url_escapes_percent_for_configparser_interpolation():
    """alembic/env.py hands the URL to set_main_option, which %-interpolates (review on #23)."""
    s = Settings(db_user="u", db_pass="100%sure", app_env="test", docs_password="x")
    assert "%25" in s.database_url()  # the percent-encoded password is what trips configparser
    with pytest.raises(ValueError, match="interpolation"):
        Config().set_main_option("sqlalchemy.url", s.database_url())
    cfg = Config()
    cfg.set_main_option("sqlalchemy.url", s.database_url().replace("%", "%%"))
    assert cfg.get_main_option("sqlalchemy.url") == s.database_url()
