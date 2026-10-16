from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

ROOT = Path(__file__).parent


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS clients(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, label TEXT NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY, name TEXT NOT NULL, location TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'active', summary TEXT NOT NULL DEFAULT '', display_order INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, title TEXT NOT NULL, details TEXT NOT NULL DEFAULT '', state TEXT NOT NULL DEFAULT 'todo', priority INTEGER NOT NULL DEFAULT 0, actor TEXT NOT NULL, blocking_reason TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, text TEXT NOT NULL, author TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS activities(id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE, entity_id TEXT, event_type TEXT NOT NULL, actor TEXT NOT NULL, client_id TEXT NOT NULL, occurred_at TEXT NOT NULL, received_at TEXT NOT NULL, summary TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS idempotency(client_id TEXT NOT NULL, key TEXT NOT NULL, fingerprint TEXT NOT NULL, status INTEGER NOT NULL, response TEXT NOT NULL, PRIMARY KEY(client_id,key));
"""


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path, timeout=10, check_same_thread=False)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db


def create_app(db_path: str | None = None, token: str | None = None) -> FastAPI:
    path = db_path or os.getenv("PMW_DB", "data/pmw.db")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript(SCHEMA)
        db.execute("BEGIN IMMEDIATE")
        columns = {r["name"] for r in db.execute("PRAGMA table_info(projects)")}
        if "user_summary" not in columns:
            db.execute("ALTER TABLE projects ADD COLUMN user_summary TEXT NOT NULL DEFAULT ''")
            # Older clients shared one summary. Preserve explicitly human-authored
            # legacy status in the human channel when its provenance is available.
            db.execute("""UPDATE projects SET user_summary=summary, summary=''
                WHERE summary<>'' AND 1=(SELECT CASE WHEN actor='human'
                AND (event_type='project.created' OR summary='Status summary updated') THEN 1 ELSE 0 END FROM activities
                WHERE project_id=projects.id AND event_type IN ('project.created','project.updated')
                ORDER BY received_at DESC,rowid DESC LIMIT 1)""")
        if "deleted_at" not in columns:
            db.execute("ALTER TABLE projects ADD COLUMN deleted_at TEXT")
        raw = token or os.getenv("PMW_TOKEN", "development-token")
        digest = hashlib.sha256(raw.encode()).hexdigest()
        db.execute("INSERT OR IGNORE INTO clients VALUES(?,?,?,0)", ("primary", digest, "primary client"))

    app = FastAPI(title="Project Manager", version="0.1.0")
    app.state.db_path = path

    def auth(authorization: str | None = Header(None)) -> dict[str, str]:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(401, "Bearer token required")
        digest = hashlib.sha256(authorization[7:].encode()).hexdigest()
        with connect(path) as db:
            row = db.execute("SELECT id,label,token_hash FROM clients WHERE token_hash=? AND revoked=0", (digest,)).fetchone()
        if not row or not hmac.compare_digest(row["token_hash"], digest):
            raise HTTPException(401, "Invalid or revoked token")
        return {"id": row["id"], "label": row["label"]}

    def rows(db: sqlite3.Connection, sql: str, args: tuple = ()) -> list[dict]:
        return [dict(r) for r in db.execute(sql, args)]

    def project_record(row) -> dict:
        record = dict(row)
        record["ai_summary"] = record["summary"]
        return record

    def active_project(db, pid):
        row = db.execute("SELECT * FROM projects WHERE id=? AND deleted_at IS NULL", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Project not found")
        return row

    def fingerprint(body: dict) -> str:
        return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @contextmanager
    def mutation(client: dict, key: str | None, body: dict, operation: str):
        if not key:
            raise HTTPException(400, "Idempotency-Key header required")
        db = connect(path)
        try:
            db.execute("BEGIN IMMEDIATE")
            old = db.execute("SELECT fingerprint,response FROM idempotency WHERE client_id=? AND key=?", (client["id"], key)).fetchone()
            fp = fingerprint({"operation": operation, "body": body})
            if old:
                if old["fingerprint"] != fp:
                    raise HTTPException(409, "Idempotency key was already used with another payload")
                yield None, json.loads(old["response"])
                db.rollback()
                return
            box: dict[str, Any] = {}
            yield db, box
            db.execute("INSERT INTO idempotency VALUES(?,?,?,?,?)", (client["id"], key, fp, 200, json.dumps(box["response"])))
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def activity(db, project_id, entity_id, kind, actor, client, summary, occurred_at=None, event_id=None):
        db.execute("INSERT INTO activities VALUES(?,?,?,?,?,?,?,?,?)", (event_id or str(uuid.uuid4()), project_id, entity_id, kind, actor, client["id"], occurred_at or utcnow(), utcnow(), summary))

    @app.get("/health")
    def health(): return {"status": "ok"}

    @app.get("/api/snapshot")
    def snapshot(client=Depends(auth)):
        with connect(path) as db:
            db.execute("BEGIN")
            projects = [project_record(r) for r in db.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY display_order,id")]
            visible = "project_id IN (SELECT id FROM projects WHERE deleted_at IS NULL)"
            tasks = rows(db, f"SELECT * FROM tasks WHERE {visible} ORDER BY priority DESC,updated_at DESC")
            notes = rows(db, f"SELECT * FROM notes WHERE {visible} ORDER BY updated_at DESC")
            activities = rows(db, f"SELECT * FROM activities WHERE {visible} ORDER BY received_at DESC,id DESC LIMIT 500")
        return {"projects": projects, "tasks": tasks, "notes": notes, "activities": activities, "server_time": utcnow()}

    @app.get("/api/activities")
    def get_activities(project_id: str | None = None, date_from: str | None = None, date_to: str | None = None, client=Depends(auth)):
        clauses, args = ["project_id IN (SELECT id FROM projects WHERE deleted_at IS NULL)"], []
        if project_id: clauses.append("project_id=?"); args.append(project_id)
        if date_from: clauses.append("occurred_at>=?"); args.append(date_from)
        if date_to: clauses.append("occurred_at<?"); args.append(date_to)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        with connect(path) as db: return rows(db, "SELECT * FROM activities" + where + " ORDER BY occurred_at DESC,received_at DESC", tuple(args))

    @app.post("/api/projects")
    async def add_project(request: Request, client=Depends(auth), key: str | None = Header(None, alias="Idempotency-Key")):
        body = await request.json(); pid = body.get("id") or str(uuid.uuid4()); now = utcnow()
        with mutation(client, key, body, "POST /api/projects") as (db, box):
            if db is None: return box
            order = body.get("display_order")
            if order is None: order = db.execute("SELECT COALESCE(MAX(display_order),-1)+1 FROM projects").fetchone()[0]
            actor = body.get("actor", "codex" if "summary" in body else "human")
            legacy = body.get("summary", "")
            user_summary = body.get("user_summary", legacy if actor == "human" else "")
            ai_summary = body.get("ai_summary", legacy if actor != "human" else "")
            if not isinstance(user_summary, str) or not isinstance(ai_summary, str):
                raise HTTPException(422, "Status must be text")
            if actor != "human" and user_summary:
                raise HTTPException(403, "Agent updates cannot replace user status")
            db.execute("INSERT INTO projects(id,name,location,state,summary,display_order,revision,updated_at,user_summary) VALUES(?,?,?,?,?,?,?,?,?)", (pid, body["name"], body.get("location", ""), body.get("state", "active"), ai_summary, order, 1, now, user_summary))
            activity(db,pid,pid,"project.created",actor,client,f"Project created: {body['name']}",body.get("occurred_at"),body.get("event_id"))
            box["response"] = project_record(db.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone())
        return box.get("response", box)

    @app.post("/api/projects/reorder")
    async def reorder_projects(request: Request, client=Depends(auth), key: str | None = Header(None, alias="Idempotency-Key")):
        body = await request.json()
        with mutation(client, key, body, "POST /api/projects/reorder") as (db, box):
            if db is None:
                return box
            requested = body.get("projects")
            if not isinstance(requested, list) or not all(isinstance(p, dict) and isinstance(p.get("id"), str) for p in requested):
                raise HTTPException(422, "projects must contain IDs and expected revisions")
            ids = [p["id"] for p in requested]
            current = {p["id"]: p for p in rows(db, "SELECT * FROM projects WHERE deleted_at IS NULL")}
            if len(ids) != len(set(ids)):
                raise HTTPException(422, "Duplicate project IDs")
            if set(ids) != set(current) or any(p.get("expected_revision") != current[p["id"]]["revision"] for p in requested):
                raise HTTPException(409, "Project list changed; refresh before reordering")
            for order, pid in enumerate(ids):
                if current[pid]["display_order"] == order:
                    continue
                db.execute("UPDATE projects SET display_order=?,revision=revision+1,updated_at=? WHERE id=?", (order, utcnow(), pid))
                activity(db, pid, pid, "project.reordered", "human", client, f"Project moved to position {order + 1}")
            box["response"] = {"projects": [project_record(p) for p in db.execute("SELECT * FROM projects WHERE deleted_at IS NULL ORDER BY display_order,id")]}
        return box["response"]

    @app.delete("/api/projects/{pid}")
    async def delete_project(pid: str, request: Request, client=Depends(auth), key: str | None = Header(None, alias="Idempotency-Key")):
        body = await request.json()
        with mutation(client, key, body, f"DELETE /api/projects/{pid}") as (db, box):
            if db is None:
                return box
            old = active_project(db, pid)
            if body.get("expected_revision") != old["revision"]:
                raise HTTPException(409, "Revision conflict; refresh before deleting")
            now = utcnow()
            db.execute("UPDATE projects SET deleted_at=?,updated_at=?,revision=revision+1 WHERE id=?", (now, now, pid))
            activity(db, pid, pid, "project.deleted", "human", client, "Project removed from dashboard")
            box["response"] = {"id": pid, "deleted": True}
        return box["response"]

    @app.patch("/api/projects/{pid}")
    async def update_project(pid: str, request: Request, client=Depends(auth), key: str | None = Header(None, alias="Idempotency-Key")):
        body = await request.json()
        with mutation(client,key,body,f"PATCH /api/projects/{pid}") as (db,box):
            if db is None: return box
            old=active_project(db, pid)
            if body.get("expected_revision") != old["revision"]: raise HTTPException(409,detail={"message":"Revision conflict","current":dict(old)})
            actor = body.get("actor", "codex" if "summary" in body or "ai_summary" in body else "human")
            allowed={k:body[k] for k in ("name","location","state","user_summary") if k in body}
            if "summary" in body:
                if "ai_summary" in body or "user_summary" in body:
                    raise HTTPException(400, "Use one explicit status channel instead of combining it with summary")
                allowed["user_summary" if actor == "human" else "summary"] = body["summary"]
            if "ai_summary" in body:
                allowed["summary"] = body["ai_summary"]
            if actor != "human" and "user_summary" in allowed:
                raise HTTPException(403, "Agent updates cannot replace user status")
            if any(not isinstance(allowed[k], str) for k in ("user_summary", "summary") if k in allowed):
                raise HTTPException(422, "Status must be text")
            if not allowed: raise HTTPException(400,"No mutable fields")
            now=utcnow(); assignments=",".join(f"{k}=?" for k in allowed)
            db.execute(f"UPDATE projects SET {assignments},revision=revision+1,updated_at=? WHERE id=?",(*allowed.values(),now,pid))
            channel = "user" if "user_summary" in allowed else "ai" if "summary" in allowed else None
            activity(db,pid,pid,"project.updated",actor,client,body.get("activity_summary") or (f"{channel.capitalize()} status updated" if channel else "Project updated"),body.get("occurred_at"),body.get("event_id"))
            box["response"]=project_record(db.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone())
        return box.get("response", box)

    @app.post("/api/projects/{pid}/tasks")
    async def add_task(pid: str, request: Request, client=Depends(auth), key: str | None = Header(None,alias="Idempotency-Key")):
        body=await request.json(); tid=body.get("id") or str(uuid.uuid4()); now=utcnow()
        with mutation(client,key,body,f"POST /api/projects/{pid}/tasks") as (db,box):
            if db is None:return box
            active_project(db, pid)
            db.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?,?,?)",(tid,pid,body["title"],body.get("details",""),body.get("state","todo"),body.get("priority",0),body.get("actor","human"),body.get("blocking_reason",""),1,now))
            activity(db,pid,tid,"task.created",body.get("actor","human"),client,f"Task added: {body['title']}",body.get("occurred_at"),body.get("event_id"))
            box["response"]=dict(db.execute("SELECT * FROM tasks WHERE id=?",(tid,)).fetchone())
        return box.get("response", box)

    @app.patch("/api/tasks/{tid}")
    async def update_task(tid: str, request: Request, client=Depends(auth), key: str | None = Header(None,alias="Idempotency-Key")):
        body=await request.json()
        with mutation(client,key,body,f"PATCH /api/tasks/{tid}") as (db,box):
            if db is None:return box
            old=db.execute("SELECT * FROM tasks WHERE id=?",(tid,)).fetchone()
            if not old:raise HTTPException(404,"Task not found")
            active_project(db, old["project_id"])
            if body.get("expected_revision") != old["revision"]:raise HTTPException(409,detail={"message":"Revision conflict","current":dict(old)})
            allowed={k:body[k] for k in ("title","details","state","priority","blocking_reason") if k in body}
            if not allowed:raise HTTPException(400,"No mutable fields")
            db.execute(f"UPDATE tasks SET {','.join(f'{k}=?' for k in allowed)},actor=?,revision=revision+1,updated_at=? WHERE id=?",(*allowed.values(),body.get("actor","human"),utcnow(),tid))
            summary=body.get("activity_summary") or f"Task changed to {body.get('state',old['state'])}"
            activity(db,old["project_id"],tid,"task.updated",body.get("actor","human"),client,summary,body.get("occurred_at"),body.get("event_id"))
            box["response"]=dict(db.execute("SELECT * FROM tasks WHERE id=?",(tid,)).fetchone())
        return box.get("response", box)

    @app.post("/api/projects/{pid}/notes")
    async def add_note(pid: str, request: Request, client=Depends(auth), key: str | None = Header(None,alias="Idempotency-Key")):
        body=await request.json(); nid=body.get("id") or str(uuid.uuid4()); now=utcnow()
        with mutation(client,key,body,f"POST /api/projects/{pid}/notes") as (db,box):
            if db is None:return box
            active_project(db, pid)
            db.execute("INSERT INTO notes VALUES(?,?,?,?,?,?)",(nid,pid,body["text"],body.get("author","human"),1,now))
            activity(db,pid,nid,"note.created",body.get("author","human"),client,"Note added",body.get("occurred_at"),body.get("event_id"))
            box["response"]=dict(db.execute("SELECT * FROM notes WHERE id=?",(nid,)).fetchone())
        return box.get("response", box)

    @app.get("/")
    def ui(): return FileResponse(ROOT / "static" / "index.html")
    @app.get("/widget")
    def widget(): return FileResponse(ROOT / "static" / "index.html")
    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    return app


app = create_app()


def main():
    import uvicorn
    uvicorn.run("pmw.server:app", host=os.getenv("PMW_HOST", "127.0.0.1"), port=int(os.getenv("PMW_PORT", "8765")), reload=False)
