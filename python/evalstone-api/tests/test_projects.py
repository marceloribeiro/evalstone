from app.services import projects as project_service


def test_create_project_slugifies_and_scopes_uniqueness(client, org, register):
    url = f"/organizations/{org['id']}/projects"
    r = client.post(url, json={"name": "RAG Bot"}, headers=org["headers"])
    assert r.status_code == 201 and r.json()["slug"] == "rag-bot"
    assert client.post(url, json={"name": "rag bot!"}, headers=org["headers"]).status_code == 409
    assert client.post(url, json={"name": "!!!"}, headers=org["headers"]).status_code == 422
    # another org may reuse the slug
    other_h, _ = register("other@org.example.com")
    o2 = client.post("/organizations", json={"name": "Other"}, headers=other_h).json()
    assert (
        client.post(
            f"/organizations/{o2['id']}/projects", json={"name": "RAG Bot"}, headers=other_h
        ).status_code
        == 201
    )
    assert len(client.get(url, headers=org["headers"]).json()) == 1


def test_project_access_follows_org_membership(client, project, register):
    pid = project["id"]
    assert client.get(f"/projects/{pid}", headers=project["headers"]).status_code == 200
    stranger_h, _ = register("s@x.example.com")
    assert client.get(f"/projects/{pid}", headers=stranger_h).status_code == 404
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{project['org']['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=project["headers"],
    )
    assert client.get(f"/projects/{pid}", headers=member_h).status_code == 200
    assert client.patch(f"/projects/{pid}", json={"name": "X"}, headers=member_h).status_code == 403
    assert (
        client.post(
            f"/organizations/{project['org']['id']}/projects", json={"name": "Y"}, headers=member_h
        ).status_code
        == 403
    )


def test_update_and_soft_delete_free_the_slug(client, project):
    pid = project["id"]
    r = client.patch(
        f"/projects/{pid}", json={"slug": "Rag V2", "description": "d"}, headers=project["headers"]
    )
    assert r.status_code == 200 and r.json()["slug"] == "rag-v2" and r.json()["description"] == "d"
    assert client.delete(f"/projects/{pid}", headers=project["headers"]).status_code == 204
    assert client.get(f"/projects/{pid}", headers=project["headers"]).status_code == 404
    again = client.post(
        f"/organizations/{project['org']['id']}/projects",
        json={"name": "Rag V2"},
        headers=project["headers"],
    )
    assert again.status_code == 201


def test_ingest_key_shown_once_resolves_and_revokes(client, project):
    pid, h = project["id"], project["headers"]
    r = client.post(f"/projects/{pid}/ingest-keys", json={"name": "ci"}, headers=h)
    assert r.status_code == 201, r.text
    created = r.json()
    secret = created["key"]
    assert secret.startswith("es_") and created["prefix"] == secret[:12]
    listed = client.get(f"/projects/{pid}/ingest-keys", headers=h).json()
    assert len(listed) == 1 and "key" not in listed[0] and listed[0]["last_used_at"] is None
    who = client.get("/ingest/whoami", headers={"Authorization": f"Bearer {secret}"})
    assert who.status_code == 200 and who.json()["id"] == pid
    assert (
        client.get(f"/projects/{pid}/ingest-keys", headers=h).json()[0]["last_used_at"] is not None
    )
    # wrong / missing / JWT-shaped tokens are rejected on the ingest surface
    assert client.get("/ingest/whoami").status_code == 401
    assert (
        client.get("/ingest/whoami", headers={"Authorization": "Bearer es_nope"}).status_code == 401
    )
    assert client.get("/ingest/whoami", headers=h).status_code == 401
    rev = client.delete(f"/projects/{pid}/ingest-keys/{created['id']}", headers=h)
    assert rev.status_code == 200 and rev.json()["revoked_at"] is not None
    assert (
        client.get("/ingest/whoami", headers={"Authorization": f"Bearer {secret}"}).status_code
        == 401
    )


def test_ingest_key_of_a_deleted_project_stops_working(client, project):
    pid, h = project["id"], project["headers"]
    secret = client.post(f"/projects/{pid}/ingest-keys", json={"name": "ci"}, headers=h).json()[
        "key"
    ]
    client.delete(f"/projects/{pid}", headers=h)
    assert (
        client.get("/ingest/whoami", headers={"Authorization": f"Bearer {secret}"}).status_code
        == 401
    )


def test_ingest_keys_need_admin(client, project, register):
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{project['org']['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=project["headers"],
    )
    assert client.get(f"/projects/{project['id']}/ingest-keys", headers=member_h).status_code == 403


def test_service_stores_only_the_hash(db, project):
    from uuid import UUID

    from app.models import IngestKey

    keys = db.query(IngestKey).all()
    assert keys == []
    p = project_service.get_project(db, UUID(project["id"]))
    from app.services import users as user_service

    u = user_service.get_user_by_email(db, "owner@acme.example.com")
    key, secret = project_service.create_ingest_key(db, project=p, created_by=u, name="x")
    assert secret not in (key.key_hash, key.prefix) and len(key.key_hash) == 64
    assert project_service.resolve_ingest_key(db, secret).id == p.id
    assert project_service.resolve_ingest_key(db, "es_other") is None
