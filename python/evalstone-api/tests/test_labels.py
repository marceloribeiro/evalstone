from evalstone.checks.human import Label as LibLabel
from evalstone.checks.human import LabelStore, output_hash

LABELS = [
    {
        "sample_id": "return-window",
        "output_hash": output_hash("30 days"),
        "value": 1.0,
        "passed": True,
        "labeler": "ada",
    },
    {
        "sample_id": "express",
        "output_hash": output_hash("no idea"),
        "value": 0.0,
        "passed": False,
        "notes": "wrong",
        "check": "helpful",
        "raw": 1,
    },
]


def _url(project, suffix=""):
    return f"/projects/{project['id']}/labels" + suffix


def test_push_list_lookup_and_export_round_trip_through_the_library(client, project, tmp_path):
    h = project["headers"]
    r = client.post(_url(project), json={"labels": LABELS}, headers=h)
    assert r.status_code == 200 and r.json() == {"upserted": 2}
    page = client.get(_url(project), headers=h).json()
    assert page["total"] == 2 and {x["sample_key"] for x in page["items"]} == {
        "return-window",
        "express",
    }
    assert all(x["labeler_user_id"] for x in page["items"])  # pushed by a member
    one = client.get(
        _url(project, "/lookup"),
        params={"sample_key": "express", "output_hash": output_hash("no idea"), "check": "helpful"},
        headers=h,
    ).json()
    assert one["passed"] is False and one["check_key"] == "helpful" and one["raw"] == 1
    miss = client.get(
        _url(project, "/lookup"),
        params={"sample_key": "express", "output_hash": output_hash("changed")},
        headers=h,
    )
    assert miss.status_code == 404  # a label never applies to a changed answer
    jsonl = client.get(_url(project, "/export"), headers=h).text
    path = tmp_path / "labels.jsonl"
    path.write_text(jsonl)
    store = LabelStore(path)  # the standalone `human` check reads exactly this
    assert len(store) == 2
    assert store.get("return-window", "30 days").passed is True
    assert store.get("express", "no idea", check="helpful").value == 0.0


def test_later_wins_within_a_push_and_across_pushes(client, project, db):
    from app.models import Label

    h = project["headers"]
    first = {**LABELS[0], "value": 0.0, "passed": False}
    client.post(_url(project), json={"labels": [first, LABELS[0]]}, headers=h)
    assert db.query(Label).count() == 1
    assert client.get(_url(project), headers=h).json()["items"][0]["passed"] is True
    client.post(_url(project), json={"labels": [first]}, headers=h)
    db.expire_all()
    assert db.query(Label).count() == 1
    assert client.get(_url(project), headers=h).json()["items"][0]["passed"] is False


def test_filters_delete_and_roles(client, project, register):
    h = project["headers"]
    client.post(_url(project), json={"labels": LABELS}, headers=h)
    assert client.get(_url(project), params={"check": "helpful"}, headers=h).json()["total"] == 1
    assert client.get(_url(project), params={"check": ""}, headers=h).json()["total"] == 1
    assert (
        client.get(_url(project), params={"sample_key": "express"}, headers=h).json()["total"] == 1
    )
    lid = client.get(_url(project), headers=h).json()["items"][0]["id"]
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{project['org']['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=h,
    )
    assert client.delete(_url(project, f"/{lid}"), headers=member_h).status_code == 403
    assert client.delete(_url(project, f"/{lid}"), headers=h).status_code == 204
    assert client.get(_url(project), headers=h).json()["total"] == 1
    secret = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "ci"}, headers=h
    ).json()["key"]
    r = client.post(
        _url(project), json={"labels": LABELS[:1]}, headers={"Authorization": f"Bearer {secret}"}
    )
    assert r.status_code == 200
    assert client.get(_url(project), headers=h).json()["items"][0]["labeler_user_id"] is None


def test_validation(client, project):
    h = project["headers"]
    bad = client.post(
        _url(project),
        json={"labels": [{"sample_id": "s", "output_hash": "h", "value": 2, "passed": True}]},
        headers=h,
    )
    assert bad.status_code == 422
    assert client.post(_url(project), json={"labels": []}, headers=h).json() == {"upserted": 0}
    lib = LibLabel(sample_id="s", output_hash=output_hash("x"), value=0.5, passed=False)
    r = client.post(_url(project), json={"labels": [lib.model_dump(mode="json")]}, headers=h)
    assert r.status_code == 200 and r.json()["upserted"] == 1
