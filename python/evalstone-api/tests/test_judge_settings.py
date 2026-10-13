from app.services import judge_settings as svc


def _prov(client, org, name):
    r = client.post(
        f"/organizations/{org['id']}/providers",
        json={"name": name, "adapter": "openai"},
        headers=org["headers"],
    )
    assert r.status_code == 201, r.text


def test_defaults_are_empty_and_put_validates_against_org_providers(client, project):
    org, pid, h = project["org"], project["id"], project["headers"]
    url = f"/projects/{pid}/judge-settings"
    assert client.get(url, headers=h).json() == {
        "project_id": pid,
        "default_model": None,
        "overrides": {},
    }
    r = client.put(url, json={"default_model": "openai/gpt-x"}, headers=h)
    assert r.status_code == 422 and "no provider named 'openai'" in r.json()["detail"]
    _prov(client, org, "openai")
    _prov(client, org, "anthropic")
    r = client.put(
        url,
        json={
            "default_model": "openai/gpt-x",
            "overrides": {"judge.helpful": "anthropic/claude-x"},
        },
        headers=h,
    )
    assert r.status_code == 200, r.text
    assert r.json()["overrides"] == {"judge.helpful": "anthropic/claude-x"}
    assert client.get(url, headers=h).json()["default_model"] == "openai/gpt-x"
    bare = client.put(url, json={"default_model": "gpt-x"}, headers=h)
    assert bare.status_code == 422 and "<provider>/<model>" in bare.json()["detail"]
    missing = client.put(url, json={"overrides": {"k": "ollama/llama"}}, headers=h)
    assert missing.status_code == 422 and "overrides['k']" in missing.json()["detail"]


def test_put_replaces_and_clears(client, project):
    org, pid, h = project["org"], project["id"], project["headers"]
    _prov(client, org, "openai")
    url = f"/projects/{pid}/judge-settings"
    client.put(url, json={"default_model": "openai/a", "overrides": {"x": "openai/b"}}, headers=h)
    r = client.put(url, json={}, headers=h)
    assert r.json() == {"project_id": pid, "default_model": None, "overrides": {}}


def test_write_needs_admin(client, project, register):
    member_h, _ = register("m@acme.example.com")
    client.post(
        f"/organizations/{project['org']['id']}/invitations",
        json={"email": "m@acme.example.com"},
        headers=project["headers"],
    )
    url = f"/projects/{project['id']}/judge-settings"
    assert client.get(url, headers=member_h).status_code == 200
    assert client.put(url, json={}, headers=member_h).status_code == 403


def test_model_for_prefers_override():
    from app.models import JudgeSettings

    s = JudgeSettings(default_model="openai/d", overrides={"rag.faithfulness": "anthropic/o"})
    assert svc.model_for(s, "rag.faithfulness") == "anthropic/o"
    assert svc.model_for(s, "judge") == "openai/d"
    assert svc.model_for(JudgeSettings(default_model=None, overrides={}), "judge") is None
