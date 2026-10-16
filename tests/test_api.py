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
