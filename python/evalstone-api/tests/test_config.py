import getpass

import pytest
from sqlalchemy.engine import make_url

from app.config import Settings, get_settings

_x = {
    "app_env": "x",
    "docs_password": "s3cret",
    "jwt_secret": "a" * 40,
}  # a non-local env with a real password


def test_tests_run_against_the_test_database():
    s = get_settings()
    assert s.is_test
    assert s.active_db_name == s.db_test_name
    assert s.database_url().endswith(f"/{s.db_test_name}")


def test_database_url_shapes():
    s = Settings(db_user="u", db_pass="", db_host="h", db_port=5, db_name="dev", **_x)
    assert s.database_url() == "postgresql+psycopg://u@h:5/dev"
    assert s.database_url("other") == "postgresql+psycopg://u@h:5/other"
    assert (
        Settings(db_user="u", db_pass="p", **_x)
        .database_url()
        .startswith("postgresql+psycopg://u:p@")
    )


def test_database_url_survives_a_generated_password_with_url_metacharacters():
    password = "p@ss:w/rd#1%x"
    s = Settings(db_user="ev@l", db_pass=password, db_host="h", db_port=5, db_name="d", **_x)
    url = make_url(s.database_url())
    assert (url.username, url.password) == ("ev@l", password)
    assert (url.host, url.port, url.database) == ("h", 5, "d")


def test_db_user_defaults_to_the_os_user_not_a_hardcoded_name():
    assert Settings.model_fields["db_user"].default == getpass.getuser()


def test_cors_origins_are_split_and_trimmed():
    assert Settings(cors_origins=" http://a , http://b,").cors_origin_list == [
        "http://a",
        "http://b",
    ]


_strong = "a" * 40


@pytest.mark.parametrize("password", ["", "change-me"])
def test_production_refuses_the_published_docs_password(password):
    with pytest.raises(ValueError, match="DOCS_PASSWORD"):
        Settings(app_env="production", docs_password=password, jwt_secret=_strong)


@pytest.mark.parametrize("secret", ["", "dev-only-change-me-dev-only-change-me"])
def test_production_refuses_the_published_jwt_secret(secret):
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(app_env="production", docs_password="s3cret", jwt_secret=secret)


def test_production_refuses_a_short_jwt_secret():
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(app_env="production", docs_password="s3cret", jwt_secret="short")
    assert Settings(app_env="production", docs_password="s3cret", jwt_secret=_strong).jwt_secret


def test_development_and_test_keep_the_default_docs_password():
    assert Settings(app_env="development").docs_password == "change-me"
    assert Settings(app_env="test", docs_password="").docs_password == ""
    assert Settings(app_env="development", jwt_secret="short").jwt_secret == "short"
