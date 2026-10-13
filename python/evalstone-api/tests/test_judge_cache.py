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


def test_lookup_cap_is_enforced_at_the_route(client, project):
    keys = [KEY] * (svc.MAX_LOOKUP_KEYS + 1)
    r = client.post(_url(project) + "/lookup", json={"keys": keys}, headers=project["headers"])
    assert r.status_code == 422


# --- regressions from the #30 review ---------------------------------------------------------


def test_reput_without_version_keeps_it_and_advances_updated_at(client, project, db):
    from app.models import JudgeCacheEntry

    h = project["headers"]
    client.put(_url(project, KEY), json={"score": SCORE, "judge_version": "abc123"}, headers=h)
    before = db.query(JudgeCacheEntry).one()
    created_at, updated_at = before.created_at, before.updated_at
    r = client.put(_url(project, KEY), json={"score": {**SCORE, "value": 0.1}}, headers=h)
    assert r.status_code == 200 and r.json()["judge_version"] == "abc123"  # not nulled
    db.expire_all()
    after = db.query(JudgeCacheEntry).one()
    assert after.created_at == created_at and after.updated_at > updated_at


def test_hits_are_counted_atomically_under_concurrent_reads(client, project):
    from concurrent.futures import ThreadPoolExecutor

    h = project["headers"]
    client.put(_url(project, KEY), json={"score": SCORE}, headers=h)
    with ThreadPoolExecutor(max_workers=8) as pool:
        codes = list(
            pool.map(lambda _: client.get(_url(project, KEY), headers=h).status_code, range(16))
        )
    assert codes == [200] * 16
    assert client.get(_url(project, KEY), headers=h).json()["hits"] == 17


def test_score_body_is_the_library_model(client, project):
    from app.schemas.labels import CachePutIn

    assert CachePutIn.model_fields["score"].annotation is Score
    extra = client.put(
        _url(project, KEY), json={"score": {**SCORE, "bogus": 1}}, headers=project["headers"]
    )
    assert extra.status_code == 201  # Score ignores unknown fields like the library does


def test_no_redundant_indexes(db):
    from sqlalchemy import text

    names = {
        r[0]
        for r in db.execute(
            text("select indexname from pg_indexes where tablename in ('labels','judge_cache')")
        )
    }
    assert names == {
        "labels_pkey",
        "judge_cache_pkey",
        "uq_judge_cache_key",
        "uq_label_sample_output",
    }
