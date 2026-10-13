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
    assert client.get(f"/projects/{other}/datasets", headers=kh).status_code == 401
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
