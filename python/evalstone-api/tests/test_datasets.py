import uuid

from evalstone._json import sha256
from evalstone.dataset import Dataset as LibDataset
from evalstone.dataset import Sample as LibSample

from app.models import Sample
from app.services import datasets as svc

RECORDS = [
    {"input": "What is 2+2?", "expected": "4", "tags": ["math", "easy"]},
    {"input": {"q": "capital of France"}, "expected": "Paris", "metadata": {"src": "wiki"}},
    {"id": "explicit-1", "input": "same", "expected": "same"},
]


def _ds(client, project, name="golden"):
    r = client.post(
        f"/projects/{project['id']}/datasets", json={"name": name}, headers=project["headers"]
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_dataset_crud_and_name_unique_per_project(client, project):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    assert (
        client.post(f"/projects/{pid}/datasets", json={"name": "golden"}, headers=h).status_code
        == 409
    )
    r = client.patch(
        f"/projects/{pid}/datasets/{did}", json={"tags": ["ci"], "description": "d"}, headers=h
    )
    assert r.status_code == 200 and r.json()["tags"] == ["ci"]
    assert [d["name"] for d in client.get(f"/projects/{pid}/datasets", headers=h).json()] == [
        "golden"
    ]
    assert client.delete(f"/projects/{pid}/datasets/{did}", headers=h).status_code == 204
    assert client.get(f"/projects/{pid}/datasets/{did}", headers=h).status_code == 404
    assert (
        client.post(f"/projects/{pid}/datasets", json={"name": "golden"}, headers=h).status_code
        == 201
    )


def test_tags_are_trimmed_and_deduplicated(client, project):
    """The web renders tags by value (chip keys, remove-by-value): duplicates would collide."""
    pid, h = project["id"], project["headers"]
    body = {"name": "t", "tags": ["ci", " ci", "", "golden"]}
    r = client.post(f"/projects/{pid}/datasets", json=body, headers=h)
    assert r.status_code == 201 and r.json()["tags"] == ["ci", "golden"]
    url = f"/projects/{pid}/datasets/{r.json()['id']}"
    assert client.patch(url, json={"tags": ["a", "a"]}, headers=h).json()["tags"] == ["a"]


def test_version_hash_matches_the_library_and_push_is_idempotent(client, project, db):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    url = f"/projects/{pid}/datasets/{did}/versions"
    r = client.post(url, json={"samples": RECORDS, "note": "first"}, headers=h)
    assert r.status_code == 201, r.text
    v1 = r.json()
    lib = LibDataset.from_records("golden", RECORDS)
    assert v1["version"] == 1 and v1["content_hash"] == lib.content_hash and v1["sample_count"] == 3
    # same content again → 200 with the same version, nothing new stored
    again = client.post(url, json={"samples": RECORDS}, headers=h)
    assert again.status_code == 200 and again.json()["id"] == v1["id"]
    assert db.query(Sample).count() == 3
    # a change → version 2; unchanged samples are shared, not duplicated
    changed = [*RECORDS[:2], {"id": "explicit-1", "input": "same", "expected": "changed"}]
    r2 = client.post(url, json={"samples": changed}, headers=h)
    assert r2.status_code == 201 and r2.json()["version"] == 2
    assert db.query(Sample).count() == 4
    assert [v["version"] for v in client.get(url, headers=h).json()] == [1, 2]
    page = client.get(f"{url}/1/samples", headers=h).json()
    assert page["total"] == 3 and [s["sample_key"] for s in page["items"]] == [
        s.id for s in lib.samples
    ]
    assert page["items"][1]["metadata"] == {"src": "wiki"} and page["items"][0]["tags"] == [
        "easy",
        "math",
    ]
    assert page["items"][0]["content_hash"] == sha256(lib.samples[0].content())
    page2 = client.get(f"{url}/2/samples?offset=2&limit=1", headers=h).json()
    assert page2["total"] == 3 and page2["items"][0]["expected"] == "changed"
    assert client.get(f"{url}/9", headers=h).status_code == 404


def test_version_validation_duplicates_empty_and_cap(client, project):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    url = f"/projects/{pid}/datasets/{did}/versions"
    dup = client.post(url, json={"samples": [{"input": "a"}, {"input": "a"}]}, headers=h)
    assert dup.status_code == 422 and "duplicate sample id" in dup.json()["detail"]
    assert client.post(url, json={"samples": []}, headers=h).status_code == 422
    big = client.post(url, json={"samples": [{"input": i} for i in range(5001)]}, headers=h)
    assert big.status_code == 422


def test_ingest_key_can_push_versions_for_its_project_only(client, project, register):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    secret = client.post(f"/projects/{pid}/ingest-keys", json={"name": "ci"}, headers=h).json()[
        "key"
    ]
    kh = {"Authorization": f"Bearer {secret}"}
    r = client.post(
        f"/projects/{pid}/datasets/{did}/versions", json={"samples": RECORDS}, headers=kh
    )
    assert r.status_code == 201 and r.json()["created_by_user_id"] is None
    assert client.get(f"/projects/{pid}/datasets", headers=kh).status_code == 200
    # the key does not open another project
    other = client.post(
        f"/organizations/{project['org']['id']}/projects", json={"name": "Other"}, headers=h
    ).json()["id"]
    assert client.get(f"/projects/{other}/datasets", headers=kh).status_code == 404  # outsider
    # and a revoked key is refused
    kid = client.get(f"/projects/{pid}/ingest-keys", headers=h).json()[0]["id"]
    client.delete(f"/projects/{pid}/ingest-keys/{kid}", headers=h)
    assert client.get(f"/projects/{pid}/datasets", headers=kh).status_code == 401
    # settings stay off-limits to keys (they are not members)
    assert client.delete(f"/projects/{pid}/datasets/{did}", headers=kh).status_code == 401


def test_members_read_and_push_admins_delete(client, project, register):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{project['org']['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=h,
    )
    assert (
        client.post(
            f"/projects/{pid}/datasets/{did}/versions", json={"samples": RECORDS}, headers=member_h
        ).status_code
        == 201
    )
    assert client.delete(f"/projects/{pid}/datasets/{did}", headers=member_h).status_code == 403
    stranger_h, _ = register("s@x.example.com")
    assert client.get(f"/projects/{pid}/datasets", headers=stranger_h).status_code == 404


def test_samples_are_shared_within_a_project_not_across(client, project, db):
    pid, h = project["id"], project["headers"]
    a, b = _ds(client, project, "a"), _ds(client, project, "b")
    for did in (a, b):
        client.post(
            f"/projects/{pid}/datasets/{did}/versions", json={"samples": RECORDS[:1]}, headers=h
        )
    assert db.query(Sample).count() == 1
    other = client.post(
        f"/organizations/{project['org']['id']}/projects", json={"name": "Other"}, headers=h
    ).json()["id"]
    od = client.post(f"/projects/{other}/datasets", json={"name": "a"}, headers=h).json()["id"]
    client.post(
        f"/projects/{other}/datasets/{od}/versions", json={"samples": RECORDS[:1]}, headers=h
    )
    assert db.query(Sample).count() == 2


def test_service_content_hash_equals_library(db):
    samples = [LibSample.model_validate(r) for r in RECORDS]
    assert svc.content_hash_of(samples) == LibDataset.from_records("x", RECORDS).content_hash
    assert svc.content_hash_of(samples) != svc.content_hash_of(
        list(reversed(samples))
    )  # order matters


def test_embedding_column_exists_and_is_empty(db, client, project):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    client.post(
        f"/projects/{pid}/datasets/{did}/versions", json={"samples": RECORDS[:1]}, headers=h
    )
    row = db.query(Sample).one()
    assert row.embedding is None
    row.embedding = [0.0] * 1536
    db.commit()
    db.refresh(row)
    assert len(row.embedding) == 1536
    assert uuid.UUID(str(row.id))


# --- regressions from the #27 review ---------------------------------------------------------


def test_concurrent_pushes_of_the_same_content_serialise(client, project, db):
    """Two CI jobs push at once: one creates version 1, the other gets it back (no 409)."""
    from concurrent.futures import ThreadPoolExecutor

    from app.models import DatasetVersion

    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    url = f"/projects/{pid}/datasets/{did}/versions"

    def push():
        return client.post(url, json={"samples": RECORDS}, headers=h).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(lambda _: push(), range(2)))
    assert statuses == [200, 201], statuses
    assert db.query(DatasetVersion).count() == 1
    assert db.query(Sample).count() == 3


def test_concurrent_new_samples_in_two_datasets_do_not_collide(client, project, db):
    from concurrent.futures import ThreadPoolExecutor

    pid, h = project["id"], project["headers"]
    a, b = _ds(client, project, "a"), _ds(client, project, "b")

    def push(did):
        return client.post(
            f"/projects/{pid}/datasets/{did}/versions", json={"samples": RECORDS}, headers=h
        ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = sorted(pool.map(push, [a, b]))
    assert statuses == [201, 201], statuses
    assert db.query(Sample).count() == 3  # shared rows, inserted once


def test_repush_refreshes_metadata_and_source_outside_the_hash(client, project):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    url = f"/projects/{pid}/datasets/{did}/versions"
    base = {"input": "q", "expected": "a"}
    v1 = client.post(url, json={"samples": [base, {"input": "other"}]}, headers=h).json()
    annotated = {**base, "metadata": {"src": "wiki", "reviewed": True}, "source": "harvested"}
    r = client.post(url, json={"samples": [annotated]}, headers=h)
    assert r.status_code == 201 and r.json()["version"] == 2  # content changed (one sample dropped)
    rows = client.get(f"{url}/2/samples", headers=h).json()["items"]
    assert (
        rows[0]["metadata"] == {"src": "wiki", "reviewed": True}
        and rows[0]["source"] == "harvested"
    )
    # the shared row was refreshed, so version 1 shows the annotation too (documented behaviour)
    v1_rows = client.get(f"{url}/{v1['version']}/samples", headers=h).json()["items"]
    assert v1_rows[0]["metadata"] == {"src": "wiki", "reviewed": True}


def test_oversized_sample_is_rejected(client, project):
    pid, h = project["id"], project["headers"]
    did = _ds(client, project)
    big = {"input": "x" * (svc.MAX_SAMPLE_BYTES + 1)}
    r = client.post(f"/projects/{pid}/datasets/{did}/versions", json={"samples": [big]}, headers=h)
    assert r.status_code == 422 and "bytes" in r.json()["detail"]


def test_version_cap_comes_from_one_constant():
    from app.schemas.datasets import VersionIn

    field = VersionIn.model_fields["samples"]
    assert any(
        getattr(m, "max_length", None) == svc.MAX_SAMPLES_PER_VERSION for m in field.metadata
    )


def test_wrong_project_ingest_key_is_an_outsider_404_not_401(client, project):
    pid, h = project["id"], project["headers"]
    secret = client.post(f"/projects/{pid}/ingest-keys", json={"name": "ci"}, headers=h).json()[
        "key"
    ]
    other = client.post(
        f"/organizations/{project['org']['id']}/projects", json={"name": "Other"}, headers=h
    ).json()["id"]
    r = client.get(f"/projects/{other}/datasets", headers={"Authorization": f"Bearer {secret}"})
    assert r.status_code == 404 and "WWW-Authenticate" not in r.headers
    bad = client.get(f"/projects/{pid}/datasets", headers={"Authorization": "Bearer es_nope"})
    assert bad.status_code == 401
