from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path


def config_dir() -> Path:
    return Path(os.getenv("PMW_CONFIG_DIR", Path.home() / ".config" / "pmw"))


def load_config() -> dict:
    path = config_dir() / "config.json"
    data = json.loads(path.read_text()) if path.exists() else {}
    data["url"] = os.getenv("PMW_URL", data.get("url", "http://127.0.0.1:8765"))
    data["token"] = os.getenv("PMW_TOKEN", data.get("token", ""))
    return data


def request(method: str, path: str, body: dict | None = None, key: str | None = None):
    cfg = load_config()
    headers = {"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"}
    if key: headers["Idempotency-Key"] = key
    req = urllib.request.Request(cfg["url"].rstrip("/") + path, data=json.dumps(body).encode() if body is not None else None, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        message = exc.read().decode()
        raise RuntimeError(f"server returned {exc.code}: {message}") from exc


def mapping() -> dict:
    path = config_dir() / "folders.json"
    return json.loads(path.read_text()) if path.exists() else {}


def project_id(explicit: str | None) -> str:
    if explicit: return explicit
    here = Path.cwd().resolve()
    candidates = [(Path(folder), pid) for folder, pid in mapping().items() if here == Path(folder) or Path(folder) in here.parents]
    if not candidates: raise RuntimeError("No project selected; pass --project or run 'pmw map set PROJECT_ID'")
    return max(candidates, key=lambda item: len(str(item[0])))[1]


def enqueue(method: str, path: str, body: dict, key: str) -> None:
    folder=config_dir(); folder.mkdir(parents=True,exist_ok=True)
    with (folder/"queue.jsonl").open("a") as f: f.write(json.dumps({"method":method,"path":path,"body":body,"key":key})+"\n")


def mutate(method: str, path: str, body: dict, queue: bool):
    key=str(uuid.uuid4()); body.setdefault("event_id",str(uuid.uuid4())); body.setdefault("occurred_at",datetime.now(timezone.utc).isoformat())
    try: return request(method,path,body,key), False
    except (urllib.error.URLError,TimeoutError,OSError) as exc:
        if not queue: raise RuntimeError(f"connection failed; write was NOT committed ({exc})") from exc
        enqueue(method,path,body,key); return {"pending":True,"message":"queued locally; run 'pmw queue flush' to retry","idempotency_key":key}, True


def output(value, as_json=False):
    if as_json: print(json.dumps(value,ensure_ascii=False,indent=2)); return
    if isinstance(value,list):
        for item in value: print(f"{item.get('id','')[:8]:8}  {item.get('state',''):14}  {item.get('title') or item.get('name') or item.get('summary','')}")
    elif isinstance(value,dict): print(value.get("message") or value.get("summary") or value.get("title") or value.get("name") or json.dumps(value,ensure_ascii=False))


def parser():
    p=argparse.ArgumentParser(prog="pmw"); p.add_argument("--json",action="store_true"); p.add_argument("--project")
    sub=p.add_subparsers(dest="command",required=True)
    c=sub.add_parser("config"); c.add_argument("url"); c.add_argument("--token",required=True)
    m=sub.add_parser("map"); ms=m.add_subparsers(dest="action",required=True); x=ms.add_parser("set"); x.add_argument("project_id"); x.add_argument("--folder",default="."); ms.add_parser("list")
    i=sub.add_parser("init"); i.add_argument("--name",required=True); i.add_argument("--location",default=""); i.add_argument("--queue",action="store_true")
    sub.add_parser("status")
    ss=sub.add_parser("status-set"); ss.add_argument("summary"); ss.add_argument("--actor",default="codex"); ss.add_argument("--revision",type=int,required=True); ss.add_argument("--queue",action="store_true")
    t=sub.add_parser("task"); ts=t.add_subparsers(dest="action",required=True)
    ts.add_parser("list"); a=ts.add_parser("add"); a.add_argument("title"); a.add_argument("--actor",default="human"); a.add_argument("--queue",action="store_true")
    for action,state in (("start","in_progress"),("done","done"),("block","blocked")):
        a=ts.add_parser(action); a.add_argument("task_id"); a.add_argument("--actor",default="codex"); a.add_argument("--revision",type=int,required=True); a.add_argument("--summary"); a.add_argument("--reason",default=""); a.add_argument("--queue",action="store_true"); a.set_defaults(state=state)
    n=sub.add_parser("note"); ns=n.add_subparsers(dest="action",required=True); ns.add_parser("list"); a=ns.add_parser("add"); a.add_argument("text"); a.add_argument("--author",default="human"); a.add_argument("--queue",action="store_true")
    act=sub.add_parser("activity"); act.add_argument("--from-date"); act.add_argument("--to-date")
    q=sub.add_parser("queue"); q.add_subparsers(dest="action",required=True).add_parser("flush")
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:
        if args.command=="config":
            d=config_dir(); d.mkdir(parents=True,exist_ok=True); (d/"config.json").write_text(json.dumps({"url":args.url,"token":args.token})); os.chmod(d/"config.json",0o600); result={"message":"Configuration saved"}
        elif args.command=="map":
            maps=mapping()
            if args.action=="set":
                maps[str(Path(args.folder).resolve())]=args.project_id; config_dir().mkdir(parents=True,exist_ok=True); (config_dir()/"folders.json").write_text(json.dumps(maps,indent=2)); result={"message":"Folder mapping saved"}
            else: result=maps
        elif args.command=="init": result,_=mutate("POST","/api/projects",{"name":args.name,"location":args.location,"actor":"human"},args.queue)
        elif args.command=="status":
            snap=request("GET","/api/snapshot"); pid=project_id(args.project); result=next((p for p in snap["projects"] if p["id"]==pid),None) or (_ for _ in ()).throw(RuntimeError("Project not found"))
        elif args.command=="status-set": result,_=mutate("PATCH",f"/api/projects/{project_id(args.project)}",{"summary":args.summary,"actor":args.actor,"expected_revision":args.revision,"activity_summary":"Status summary updated"},args.queue)
        elif args.command=="task":
            pid=project_id(args.project)
            if args.action=="list": result=[t for t in request("GET","/api/snapshot")["tasks"] if t["project_id"]==pid]
            elif args.action=="add": result,_=mutate("POST",f"/api/projects/{pid}/tasks",{"title":args.title,"actor":args.actor},args.queue)
            else:
                body={"state":args.state,"actor":args.actor,"expected_revision":args.revision,"activity_summary":args.summary or f"Task {args.state}","blocking_reason":args.reason}; result,_=mutate("PATCH",f"/api/tasks/{args.task_id}",body,args.queue)
        elif args.command=="note":
            pid=project_id(args.project)
            if args.action=="list": result=[n for n in request("GET","/api/snapshot")["notes"] if n["project_id"]==pid]
            else: result,_=mutate("POST",f"/api/projects/{pid}/notes",{"text":args.text,"author":args.author},args.queue)
        elif args.command=="activity":
            from urllib.parse import urlencode
            params={k:v for k,v in {"project_id":project_id(args.project),"date_from":args.from_date,"date_to":args.to_date}.items() if v}; result=request("GET","/api/activities?"+urlencode(params))
        elif args.command=="queue":
            path=config_dir()/"queue.jsonl"; ops=[json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []; remaining=[]; sent=0
            for op in ops:
                try: request(op["method"],op["path"],op["body"],op["key"]); sent+=1
                except Exception as exc: op["error"]=str(exc); remaining.append(op); break
            remaining.extend(ops[sent+len(remaining):]); path.write_text("".join(json.dumps(x)+"\n" for x in remaining)); result={"message":f"replayed {sent}; {len(remaining)} pending","sent":sent,"pending":len(remaining)}
        output(result,args.json)
    except Exception as exc:
        print(f"pmw: {exc}",file=sys.stderr); return 1
    return 0


if __name__=="__main__": raise SystemExit(main())
