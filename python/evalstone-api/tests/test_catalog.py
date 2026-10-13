from evalstone.config import FACTORIES

from app.services import catalog as svc


def _url(org):
    return f"/organizations/{org['id']}/checks"


def test_builtins_mirror_the_installed_library(client, org):
    r = client.get("/catalog/checks", headers=org["headers"])
    assert r.status_code == 200
    rows = {x["type"]: x for x in r.json()}
    assert set(rows) == set(FACTORIES)  # every factory, nothing else
    judge = rows["judge"]
    assert judge["kind"] == "judge" and judge["library_version"]
    names = {p["name"]: p for p in judge["params"]}
    assert names["rubric"]["required"] is True and names["scale"]["default"] == 5
    assert "key" not in names
    assert rows["rag.faithfulness"]["kind"] == "rag" and rows["exact"]["kind"] == "deterministic"
    assert rows["safety.refusal"]["kind"] == "safety"
    assert client.get("/catalog/checks").status_code == 401


def test_create_validates_against_the_factory_signature(client, org):
    h = org["headers"]
    ok = client.post(
        _url(org),
        json={
            "key": "helpful",
            "type": "judge",
            "params": {"rubric": "Is it helpful?", "scale": 3},
            "description": "d",
        },
        headers=h,
    )
    assert ok.status_code == 201, ok.text
    assert ok.json()["kind"] == "judge" and ok.json()["current_version"] == 1
    assert (
        client.post(
            _url(org),
            json={"key": "helpful", "type": "judge", "params": {"rubric": "x"}},
            headers=h,
        ).status_code
        == 409
    )
    bad_type = client.post(_url(org), json={"key": "x", "type": "nope", "params": {}}, headers=h)
    assert bad_type.status_code == 422 and "unknown check type" in bad_type.json()["detail"]
    bad_param = client.post(
        _url(org),
        json={"key": "x", "type": "judge", "params": {"rubric": "r", "bogus": 1}},
        headers=h,
    )
    assert bad_param.status_code == 422 and "do not fit judge" in bad_param.json()["detail"]
    missing = client.post(_url(org), json={"key": "x", "type": "judge", "params": {}}, headers=h)
    assert missing.status_code == 422
    server_side = client.post(
        _url(org),
        json={"key": "x", "type": "human", "params": {"labels": "/etc/passwd"}},
        headers=h,
    )
    assert server_side.status_code == 422 and "files or code" in server_side.json()["detail"]
    assert (
        client.post(
            _url(org), json={"key": "Bad Key", "type": "exact", "params": {}}, headers=h
        ).status_code
        == 422
    )
    assert (
        client.post(
            _url(org), json={"key": "x", "type": "exact", "params": {"key": "y"}}, headers=h
        ).status_code
        == 422
    )


def test_update_versions_only_on_content_change(client, org):
    h = org["headers"]
    cid = client.post(
        _url(org), json={"key": "helpful", "type": "judge", "params": {"rubric": "v1"}}, headers=h
    ).json()["id"]
    r = client.put(f"{_url(org)}/{cid}", json={"description": "clearer"}, headers=h)
    assert r.status_code == 200 and r.json()["current_version"] == 1
    r = client.put(
        f"{_url(org)}/{cid}",
        json={"params": {"rubric": "v2", "scale": 5}, "note": "tightened"},
        headers=h,
    )
    assert (
        r.status_code == 201
        and r.json()["current_version"] == 2
        and r.json()["params"]["rubric"] == "v2"
    )
    same = client.put(
        f"{_url(org)}/{cid}", json={"params": {"rubric": "v2", "scale": 5}}, headers=h
    )
    assert same.status_code == 200 and same.json()["current_version"] == 2  # no-op content
    versions = client.get(f"{_url(org)}/{cid}/versions", headers=h).json()
    assert [(v["version"], v["params"]["rubric"], v["note"]) for v in versions] == [
        (1, "v1", "created"),
        (2, "v2", "tightened"),
    ]
    assert versions[0]["content_hash"] != versions[1]["content_hash"]
    assert versions[1]["content_hash"] == svc.content_hash("judge", {"rubric": "v2", "scale": 5})
    assert client.get(f"{_url(org)}/{cid}/versions/1", headers=h).json()["type"] == "judge"
    assert client.get(f"{_url(org)}/{cid}/versions/9", headers=h).status_code == 404
    bad = client.put(
        f"{_url(org)}/{cid}", json={"type": "exact", "params": {"rubric": "x"}}, headers=h
    )
    assert bad.status_code == 422  # the new type must accept the params


def test_yaml_block_roles_and_delete(client, org, register):
    h = org["headers"]
    client.post(
        _url(org), json={"key": "short", "type": "length", "params": {"max_words": 40}}, headers=h
    )
    client.post(
        _url(org), json={"key": "helpful", "type": "judge", "params": {"rubric": "r"}}, headers=h
    )
    block = client.get(f"{_url(org)}/yaml", headers=h).json()["checks"]
    assert block == {
        "helpful": {"type": "judge", "rubric": "r"},
        "short": {"type": "length", "max_words": 40},
    }
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{org['id']}/invitations", json={"email": "m@acme.example.com"}, headers=h
    )
    assert client.get(_url(org), headers=member_h).status_code == 200
    assert (
        client.post(
            _url(org), json={"key": "x", "type": "exact", "params": {}}, headers=member_h
        ).status_code
        == 403
    )
    cid = client.get(_url(org), headers=h).json()[0]["id"]
    assert client.delete(f"{_url(org)}/{cid}", headers=member_h).status_code == 403
    assert client.delete(f"{_url(org)}/{cid}", headers=h).status_code == 204
    assert client.get(f"{_url(org)}/{cid}", headers=h).status_code == 404
    assert (
        client.post(
            _url(org),
            json={"key": "helpful", "type": "judge", "params": {"rubric": "again"}},
            headers=h,
        ).status_code
        == 201
    )
    stranger_h, _ = register("s@x.example.com")
    assert client.get(_url(org), headers=stranger_h).status_code == 404


def test_params_size_cap(client, org):
    big = {"rubric": "x" * (svc.MAX_PARAMS_BYTES + 1)}
    r = client.post(
        _url(org), json={"key": "x", "type": "judge", "params": big}, headers=org["headers"]
    )
    assert r.status_code == 422 and "bytes" in r.json()["detail"]
