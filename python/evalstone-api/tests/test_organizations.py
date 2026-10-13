import pytest

from app.errors import Invalid
from app.models import Role
from app.services import organizations as org_service
from app.services import users as user_service


def _members(client, org):
    return client.get(f"/organizations/{org['id']}/members", headers=org["headers"]).json()


def test_creator_becomes_owner_and_lists_their_orgs(client, org):
    members = _members(client, org)
    assert [(m["role"], m["user"]["email"]) for m in members] == [
        ("owner", "owner@acme.example.com")
    ]
    mine = client.get("/organizations", headers=org["headers"]).json()
    assert [o["id"] for o in mine] == [org["id"]]


def test_outsiders_get_404_not_403(client, org, register):
    other, _ = register("stranger@x.example.com")
    assert client.get(f"/organizations/{org['id']}", headers=other).status_code == 404
    assert client.get(f"/organizations/{org['id']}/members", headers=other).status_code == 404
    assert client.get("/organizations", headers=other).json() == []


def test_update_needs_admin_and_delete_needs_owner(client, org, register):
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=org["headers"],
    )
    url = f"/organizations/{org['id']}"
    assert client.patch(url, json={"name": "Acme 2"}, headers=member_h).status_code == 403
    r = client.patch(url, json={"name": "Acme 2"}, headers=org["headers"])
    assert r.status_code == 200 and r.json()["name"] == "Acme 2"
    # promote to admin: can edit, still cannot delete
    mid = next(m["id"] for m in _members(client, org) if m["role"] == "member")
    r = client.patch(f"{url}/members/{mid}", json={"role": "admin"}, headers=org["headers"])
    assert r.status_code == 200 and r.json()["role"] == "admin"
    assert client.patch(url, json={"name": "Acme 3"}, headers=member_h).status_code == 200
    assert client.delete(url, headers=member_h).status_code == 403
    assert client.delete(url, headers=org["headers"]).status_code == 204
    assert client.get(url, headers=org["headers"]).status_code == 404


def test_invite_existing_user_joins_immediately(client, org, register):
    existing_h, _ = register("exists@acme.example.com")
    r = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "Exists@acme.example.com", "role": "admin"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["status"] == "accepted" and r.json()["email"] == "exists@acme.example.com"
    assert client.get(f"/organizations/{org['id']}", headers=existing_h).status_code == 200
    roles = {m["user"]["email"]: m["role"] for m in _members(client, org)}
    assert roles["exists@acme.example.com"] == "admin"
    again = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "exists@acme.example.com"},
        headers=org["headers"],
    )
    assert again.status_code == 409


def test_invite_unknown_email_is_pending_until_register(client, org, register):
    r = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "later@acme.example.com"},
        headers=org["headers"],
    )
    assert r.status_code == 201 and r.json()["status"] == "pending"
    listed = client.get(f"/organizations/{org['id']}/invitations", headers=org["headers"]).json()
    assert [i["status"] for i in listed] == ["pending"]
    dup = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "LATER@acme.example.com"},
        headers=org["headers"],
    )
    assert dup.status_code == 409
    # the ORGANIZATION_BASED rule: registering with the invited email auto-joins as member
    later_h, _ = register("Later@acme.example.com")
    assert client.get(f"/organizations/{org['id']}", headers=later_h).status_code == 200
    roles = {m["user"]["email"]: m["role"] for m in _members(client, org)}
    assert roles["later@acme.example.com"] == "member"
    listed = client.get(f"/organizations/{org['id']}/invitations", headers=org["headers"]).json()
    assert [i["status"] for i in listed] == ["accepted"]
    gone = client.delete(
        f"/organizations/{org['id']}/invitations/{listed[0]['id']}", headers=org["headers"]
    )
    assert gone.status_code == 422  # accepted invitations cannot be revoked


def test_revoked_invitation_does_not_auto_join(client, org, register):
    inv = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "no@acme.example.com"},
        headers=org["headers"],
    ).json()
    assert (
        client.delete(
            f"/organizations/{org['id']}/invitations/{inv['id']}", headers=org["headers"]
        ).status_code
        == 204
    )
    no_h, _ = register("no@acme.example.com")
    assert client.get(f"/organizations/{org['id']}", headers=no_h).status_code == 404


def test_invitations_cannot_grant_ownership_and_need_admin(client, org, register):
    r = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "o@acme.example.com", "role": "owner"},
        headers=org["headers"],
    )
    assert r.status_code == 422
    member_h, _ = register("plain@acme.example.com")
    client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "plain@acme.example.com"},
        headers=org["headers"],
    )
    r = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "x@acme.example.com"},
        headers=member_h,
    )
    assert r.status_code == 403


def test_last_owner_cannot_be_demoted_or_removed(client, org):
    owner_member = _members(client, org)[0]
    url = f"/organizations/{org['id']}/members/{owner_member['id']}"
    assert client.patch(url, json={"role": "admin"}, headers=org["headers"]).status_code == 422
    assert client.delete(url, headers=org["headers"]).status_code == 422


def test_only_owners_touch_ownership(client, org, register):
    admin_h, _ = register("admin@acme.example.com")
    other_h, _ = register("other@acme.example.com")
    for e in ("admin@acme.example.com", "other@acme.example.com"):
        client.post(
            f"/organizations/{org['id']}/invitations", json={"email": e}, headers=org["headers"]
        )
    ids = {m["user"]["email"]: m["id"] for m in _members(client, org)}
    base = f"/organizations/{org['id']}/members"
    client.patch(
        f"{base}/{ids['admin@acme.example.com']}", json={"role": "admin"}, headers=org["headers"]
    )
    # an admin cannot mint an owner, nor touch the owner
    assert (
        client.patch(
            f"{base}/{ids['other@acme.example.com']}", json={"role": "owner"}, headers=admin_h
        ).status_code
        == 403
    )
    assert (
        client.delete(f"{base}/{ids['owner@acme.example.com']}", headers=admin_h).status_code == 403
    )
    # but can remove a member
    assert (
        client.delete(f"{base}/{ids['other@acme.example.com']}", headers=admin_h).status_code == 204
    )
    assert client.get(f"/organizations/{org['id']}", headers=other_h).status_code == 404
    # the owner promotes the admin to owner, then may step down
    assert (
        client.patch(
            f"{base}/{ids['admin@acme.example.com']}",
            json={"role": "owner"},
            headers=org["headers"],
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{base}/{ids['owner@acme.example.com']}",
            json={"role": "member"},
            headers=org["headers"],
        ).status_code
        == 200
    )


def test_service_guards_last_owner(db):
    owner = user_service.register(db, email="o@svc.example.com", password="password123")
    o = org_service.create(db, owner=owner, name="Svc")
    m = org_service.get_membership(db, o.id, owner.id)
    assert m.role == Role.OWNER
    with pytest.raises(Invalid):
        org_service.remove_member(db, actor_role=Role.OWNER, member=m)


def test_removed_member_can_be_reinvited(client, org, register):
    """Membership is soft-deleted and (org, user) is unique: re-inviting revives the row."""
    back_h, _ = register("back@acme.example.com")
    inv_url = f"/organizations/{org['id']}/invitations"
    client.post(inv_url, json={"email": "back@acme.example.com"}, headers=org["headers"])
    mid = next(
        m["id"] for m in _members(client, org) if m["user"]["email"] == "back@acme.example.com"
    )
    assert (
        client.delete(
            f"/organizations/{org['id']}/members/{mid}", headers=org["headers"]
        ).status_code
        == 204
    )
    assert client.get(f"/organizations/{org['id']}", headers=back_h).status_code == 404
    r = client.post(
        inv_url, json={"email": "back@acme.example.com", "role": "admin"}, headers=org["headers"]
    )
    assert r.status_code == 201, r.text
    assert client.get(f"/organizations/{org['id']}", headers=back_h).status_code == 200
    roles = {m["user"]["email"]: m["role"] for m in _members(client, org)}
    assert roles["back@acme.example.com"] == "admin" and len(roles) == 2


def test_deleting_an_org_retires_projects_and_revokes_ingest_keys(client, project):
    org = project["org"]
    secret = client.post(
        f"/projects/{project['id']}/ingest-keys", json={"name": "ci"}, headers=org["headers"]
    ).json()["key"]
    assert (
        client.get("/ingest/whoami", headers={"Authorization": f"Bearer {secret}"}).status_code
        == 200
    )
    assert client.delete(f"/organizations/{org['id']}", headers=org["headers"]).status_code == 204
    assert (
        client.get("/ingest/whoami", headers={"Authorization": f"Bearer {secret}"}).status_code
        == 401
    )
    assert client.get(f"/projects/{project['id']}", headers=org["headers"]).status_code == 404


def test_invitation_status_is_computed_from_accepted_at(client, org):
    r = client.post(
        f"/organizations/{org['id']}/invitations",
        json={"email": "c@acme.example.com"},
        headers=org["headers"],
    ).json()
    assert r["status"] == "pending" and r["accepted_at"] is None
