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
            projects = rows(db, "SELECT * FROM projects ORDER BY display_order,id")
            tasks = rows(db, "SELECT * FROM tasks ORDER BY priority DESC,updated_at DESC")
            notes = rows(db, "SELECT * FROM notes ORDER BY updated_at DESC")
            activities = rows(db, "SELECT * FROM activities ORDER BY received_at DESC,id DESC LIMIT 500")
        return {"projects": projects, "tasks": tasks, "notes": notes, "activities": activities, "server_time": utcnow()}

    @app.get("/api/activities")
    def get_activities(project_id: str | None = None, date_from: str | None = None, date_to: str | None = None, client=Depends(auth)):
        clauses, args = [], []
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
            db.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?,?)", (pid, body["name"], body.get("location", ""), body.get("state", "active"), body.get("summary", ""), order, 1, now))
            activity(db,pid,pid,"project.created",body.get("actor","human"),client,f"Project created: {body['name']}",body.get("occurred_at"),body.get("event_id"))
            box["response"] = dict(db.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone())
        return box.get("response", box)

    @app.patch("/api/projects/{pid}")
    async def update_project(pid: str, request: Request, client=Depends(auth), key: str | None = Header(None, alias="Idempotency-Key")):
        body = await request.json()
        with mutation(client,key,body,f"PATCH /api/projects/{pid}") as (db,box):
            if db is None: return box
            old=db.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone()
            if not old: raise HTTPException(404,"Project not found")
            if body.get("expected_revision") != old["revision"]: raise HTTPException(409,detail={"message":"Revision conflict","current":dict(old)})
            allowed={k:body[k] for k in ("name","location","state","summary","display_order") if k in body}
            if not allowed: raise HTTPException(400,"No mutable fields")
            now=utcnow(); assignments=",".join(f"{k}=?" for k in allowed)
            db.execute(f"UPDATE projects SET {assignments},revision=revision+1,updated_at=? WHERE id=?",(*allowed.values(),now,pid))
            activity(db,pid,pid,"project.updated",body.get("actor","human"),client,body.get("activity_summary") or "Project updated",body.get("occurred_at"),body.get("event_id"))
            box["response"]=dict(db.execute("SELECT * FROM projects WHERE id=?",(pid,)).fetchone())
        return box.get("response", box)

    @app.post("/api/projects/{pid}/tasks")
    async def add_task(pid: str, request: Request, client=Depends(auth), key: str | None = Header(None,alias="Idempotency-Key")):
        body=await request.json(); tid=body.get("id") or str(uuid.uuid4()); now=utcnow()
        with mutation(client,key,body,f"POST /api/projects/{pid}/tasks") as (db,box):
            if db is None:return box
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
