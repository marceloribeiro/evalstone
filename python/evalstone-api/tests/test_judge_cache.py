from evalstone._json import sha256
from evalstone.score import Score

from app.services import judge_cache as svc

KEY = sha256({"j": "abc123", "u": "rubric + input + output"})
SCORE = {"value": 0.75, "passed": True, "reason": "good", "raw": {"score": 4, "scale": 5}}


def _url(project, key=""):
    return f"/projects/{project['id']}/judge-cache" + (f"/{key}" if key else "")


def test_put_get_round_trip_and_replace(client, project):
    h = project["headers"]
    assert client.get(_url(project, KEY), headers=h).status_code == 404
    r = client.put(_url(project, KEY), json={"score": SCORE, "judge_version": "abc123"}, headers=h)
    assert r.status_code == 201, r.text
    got = client.get(_url(project, KEY), headers=h).json()
    assert Score.model_validate(got["score"]) == Score.model_validate(SCORE)  # the library's shape
    assert got["hits"] == 1 and got["last_hit_at"] and got["judge_version"] == "abc123"
    again = client.put(_url(project, KEY), json={"score": {**SCORE, "value": 0.5}}, headers=h)
    assert again.status_code == 200 and again.json()["score"]["value"] == 0.5


def test_lookup_many_and_key_validation(client, project):
    h = project["headers"]
    other = sha256({"j": "abc123", "u": "another prompt"})
    client.put(_url(project, KEY), json={"score": SCORE}, headers=h)
    r = client.post(_url(project) + "/lookup", json={"keys": [KEY, other]}, headers=h)
    assert r.status_code == 200 and set(r.json()) == {KEY}
    assert client.get(_url(project, "not-a-hash"), headers=h).status_code == 422
    assert client.put(_url(project, "x" * 64), json={"score": SCORE}, headers=h).status_code == 422
    bad = client.put(_url(project, KEY), json={"score": {"value": 2, "passed": True}}, headers=h)
    assert bad.status_code == 422


def test_cache_is_per_project_and_open_to_ingest_keys(client, project, register):
    h = project["headers"]
    secret = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "ci"}, headers=h
    ).json()["key"]
    kh = {"Authorization": f"Bearer {secret}"}
    assert client.put(_url(project, KEY), json={"score": SCORE}, headers=kh).status_code == 201
    assert client.get(_url(project, KEY), headers=kh).status_code == 200
    other = client.post(
        f"/organizations/{project['org']['id']}/projects", json={"name": "Other"}, headers=h
    ).json()["id"]
    assert client.get(f"/projects/{other}/judge-cache/{KEY}", headers=h).status_code == 404


def test_lookup_cap(db, project):
    from uuid import UUID

    import pytest

    from app.errors import Invalid
    from app.services import projects as project_service

    p = project_service.get_project(db, UUID(project["id"]))
    with pytest.raises(Invalid):
        svc.lookup(db, p, [KEY] * (svc.MAX_LOOKUP_KEYS + 1))
