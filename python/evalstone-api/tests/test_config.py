from app.config import Settings, get_settings


def test_tests_run_against_the_test_database():
    s = get_settings()
    assert s.is_test
    assert s.active_db_name == s.db_test_name
    assert s.database_url().endswith(f"/{s.db_test_name}")


def test_database_url_shapes():
    s = Settings(db_user="u", db_pass="", db_host="h", db_port=5, db_name="dev", app_env="x")
    assert s.database_url() == "postgresql+psycopg://u@h:5/dev"
    assert s.database_url("other") == "postgresql+psycopg://u@h:5/other"
    assert (
        Settings(db_user="u", db_pass="p", app_env="x")
        .database_url()
        .startswith("postgresql+psycopg://u:p@")
    )


def test_cors_origins_are_split_and_trimmed():
    assert Settings(cors_origins=" http://a , http://b,").cors_origin_list == [
        "http://a",
        "http://b",
    ]
