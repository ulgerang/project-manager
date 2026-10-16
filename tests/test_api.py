import importlib
import os

from fastapi.testclient import TestClient


def client(tmp_path):
    os.environ["PMW_DB"] = str(tmp_path / "test.db")
    os.environ["PMW_TOKEN"] = "secret"
    import pmw.server
    return TestClient(pmw.server.create_app(os.environ["PMW_DB"], "secret"))


def headers(key="one", token="secret"):
    return {"Authorization": f"Bearer {token}", "Idempotency-Key": key}


def test_auth_atomic_history_idempotency_and_conflict(tmp_path):
    c=client(tmp_path)
    assert c.get("/api/snapshot").status_code == 401
    assert c.get("/api/snapshot",headers=headers(token="wrong")).status_code == 401
    body={"id":"p1","name":"Demo","summary":"start"}
    first=c.post("/api/projects",json=body,headers=headers()).json()
    again=c.post("/api/projects",json=body,headers=headers()).json()
    assert first == again
    assert len(c.get("/api/snapshot",headers=headers()).json()["activities"]) == 1
    assert c.post("/api/projects",json={"name":"different"},headers=headers()).status_code == 409
    changed=c.patch("/api/projects/p1",json={"summary":"new","expected_revision":1},headers=headers("two"))
    assert changed.status_code == 200 and changed.json()["revision"] == 2
    assert c.patch("/api/projects/p1",json={"summary":"lost","expected_revision":1},headers=headers("three")).status_code == 409
    snap=c.get("/api/snapshot",headers=headers()).json()
    assert snap["projects"][0]["summary"] == "new" and len(snap["activities"]) == 2


def test_persistence_and_activity_filter(tmp_path):
    db=str(tmp_path/"persist.db")
    c=TestClient(__import__("pmw.server",fromlist=["create_app"]).create_app(db,"secret"))
    c.post("/api/projects",json={"id":"p1","name":"Persist"},headers=headers())
    c.close()
    c2=TestClient(__import__("pmw.server",fromlist=["create_app"]).create_app(db,"secret"))
    assert c2.get("/api/snapshot",headers=headers()).json()["projects"][0]["name"] == "Persist"
    assert len(c2.get("/api/activities?project_id=p1&date_from=2000-01-01",headers=headers()).json()) == 1


def test_idempotency_keys_include_target_resource(tmp_path):
    c = client(tmp_path)
    c.post("/api/projects", json={"id":"p1","name":"One"}, headers=headers("p1"))
    c.post("/api/projects", json={"id":"p2","name":"Two"}, headers=headers("p2"))
    body = {"summary":"Updated", "expected_revision":1}
    assert c.patch("/api/projects/p1", json=body, headers=headers("shared")).status_code == 200
    assert c.patch("/api/projects/p2", json=body, headers=headers("shared")).status_code == 409
    projects = c.get("/api/snapshot", headers=headers()).json()["projects"]
    assert next(p for p in projects if p["id"] == "p2")["summary"] == ""


def test_user_and_ai_status_are_independent_and_persistent(tmp_path):
    c = client(tmp_path)
    c.post("/api/projects", json={"id":"p1", "name":"Demo"}, headers=headers("create"))
    ai = c.patch("/api/projects/p1", json={"summary":"AI first", "actor":"codex", "expected_revision":1}, headers=headers("ai"))
    assert ai.json()["ai_summary"] == "AI first" and ai.json()["user_summary"] == ""
    human_body = {"user_summary":"My priority\nNext step", "actor":"human", "expected_revision":2}
    human = c.patch("/api/projects/p1", json=human_body, headers=headers("human"))
    assert human.json()["ai_summary"] == "AI first"
    updated = c.patch("/api/projects/p1", json={"summary":"AI second", "actor":"claude-code", "expected_revision":3}, headers=headers("ai2"))
    assert updated.json()["user_summary"] == human_body["user_summary"]
    assert updated.json()["summary"] == updated.json()["ai_summary"] == "AI second"
    assert c.patch("/api/projects/p1", json=human_body, headers=headers("human")).json() == human.json()
    assert c.patch("/api/projects/p1", json={"user_summary":"Overwrite", "actor":"codex", "expected_revision":4}, headers=headers("denied")).status_code == 403
    assert c.patch("/api/projects/p1", json=human_body, headers=headers("stale")).status_code == 409
    from pmw.server import create_app
    restarted = TestClient(create_app(str(tmp_path / "test.db"), "secret"))
    project = restarted.get("/api/snapshot", headers=headers()).json()["projects"][0]
    assert project["user_summary"] == human_body["user_summary"] and project["ai_summary"] == "AI second"
    cleared = restarted.patch("/api/projects/p1", json={"user_summary":"", "actor":"human", "expected_revision":4}, headers=headers("clear"))
    assert cleared.json()["user_summary"] == "" and cleared.json()["ai_summary"] == "AI second"


def test_reorder_is_atomic_and_rejects_changed_membership(tmp_path):
    c = client(tmp_path)
    for pid in ("p1", "p2", "p3"):
        c.post("/api/projects", json={"id":pid, "name":pid}, headers=headers(pid))
    def snapshot():
        return c.get("/api/snapshot", headers=headers()).json()
    body = {"projects":[{"id":pid, "expected_revision":1} for pid in ("p3", "p1", "p2")]}
    invalid = {"projects":[{"id":"p3", "expected_revision":1}, {"id":"p1", "expected_revision":999}, {"id":"p2", "expected_revision":1}]}
    assert c.post("/api/projects/reorder", json=invalid, headers=headers("stale")).status_code == 409
    assert [p["id"] for p in snapshot()["projects"]] == ["p1", "p2", "p3"]
    assert len(snapshot()["activities"]) == 3
    reordered = c.post("/api/projects/reorder", json=body, headers=headers("reorder"))
    assert reordered.status_code == 200
    assert [p["id"] for p in reordered.json()["projects"]] == ["p3", "p1", "p2"]
    assert c.post("/api/projects/reorder", json=body, headers=headers("reorder")).json() == reordered.json()
    assert len(snapshot()["activities"]) == 6
    assert c.post("/api/projects/reorder", json={"projects":[{"id":"p1"}, {"id":"p1"}]}, headers=headers("duplicate")).status_code == 422
    current = snapshot()["projects"]
    c.post("/api/projects", json={"id":"p4", "name":"Added elsewhere"}, headers=headers("new"))
    stale_members = {"projects":[{"id":p["id"], "expected_revision":p["revision"]} for p in current]}
    assert c.post("/api/projects/reorder", json=stale_members, headers=headers("missing")).status_code == 409
    assert [p["id"] for p in snapshot()["projects"]] == ["p3", "p1", "p2", "p4"]


def test_delete_hides_children_preserves_history_and_replays(tmp_path):
    c = client(tmp_path)
    c.post("/api/projects", json={"id":"p1", "name":"Demo"}, headers=headers("create"))
    task = c.post("/api/projects/p1/tasks", json={"title":"Keep task history"}, headers=headers("task")).json()
    c.post("/api/projects/p1/notes", json={"text":"Keep human note"}, headers=headers("note"))
    assert c.request("DELETE", "/api/projects/p1", json={"expected_revision":0}, headers=headers("stale")).status_code == 409
    body = {"expected_revision":1}
    removed = c.request("DELETE", "/api/projects/p1", json=body, headers=headers("delete"))
    assert removed.status_code == 200
    assert c.request("DELETE", "/api/projects/p1", json=body, headers=headers("delete")).json() == removed.json()
    snap = c.get("/api/snapshot", headers=headers()).json()
    assert not any(snap[k] for k in ("projects", "tasks", "notes", "activities"))
    assert c.get("/api/activities", headers=headers()).json() == []
    assert c.post("/api/projects/p1/tasks", json={"title":"Too late"}, headers=headers("late-task")).status_code == 404
    assert c.patch(f"/api/tasks/{task['id']}", json={"state":"done", "expected_revision":1}, headers=headers("late-edit")).status_code == 404
    from pmw.server import connect, create_app
    with connect(str(tmp_path / "test.db")) as db:
        assert db.execute("SELECT COUNT(*) FROM notes").fetchone()[0] == 1
        assert db.execute("SELECT COUNT(*) FROM activities WHERE event_type='project.deleted'").fetchone()[0] == 1
    restarted = TestClient(create_app(str(tmp_path / "test.db"), "secret"))
    assert restarted.get("/api/snapshot", headers=headers()).json()["projects"] == []


def test_legacy_status_migration_runs_once(tmp_path):
    from pmw.server import connect, create_app, SCHEMA
    path = str(tmp_path / "legacy.db")
    with connect(path) as db:
        db.executescript(SCHEMA)
        db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?)", ("p1", "Human", "", "active", "My original status", 0, 1, "2026-10-01T00:00:00Z"))
        db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?)", ("p2", "Agent", "", "active", "Agent original status", 1, 1, "2026-10-01T00:00:00Z"))
        for pid, actor in (("p1", "human"), ("p2", "codex")):
            db.execute("INSERT INTO activities VALUES(?,?,?,?,?,?,?,?,?)", (pid, pid, pid, "project.updated", actor, "primary", "2026-10-01T00:00:00Z", "2026-10-01T00:00:00Z", "Status summary updated"))
    for _ in range(2):
        c = TestClient(create_app(path, "secret"))
        projects = c.get("/api/snapshot", headers=headers()).json()["projects"]
        assert projects[0]["user_summary"] == "My original status" and projects[0]["ai_summary"] == ""
        assert projects[1]["user_summary"] == "" and projects[1]["ai_summary"] == "Agent original status"
