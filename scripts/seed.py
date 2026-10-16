#!/usr/bin/env python3
"""Create seven explicitly synthetic projects through the public API."""
import json, os, urllib.request, uuid

URL=os.getenv("PMW_URL","http://127.0.0.1:8765"); TOKEN=os.getenv("PMW_TOKEN","development-token")
projects=[("Aurora Docs","문서 검색 품질 검증 중"),("Beacon API","인증 경계 구현 완료"),("Cedar Mobile","내비게이션 시안 검토 필요"),("Drift Analytics","이벤트 스키마 정리 중"),("Ember Studio","내보내기 오류 재현 중"),("Fjord Ops","백업 훈련 대기"),("Grove Learn","콘텐츠 모델 설계 중")]
def post(path,body):
 req=urllib.request.Request(URL+path,data=json.dumps(body).encode(),headers={"Authorization":f"Bearer {TOKEN}","Content-Type":"application/json","Idempotency-Key":str(uuid.uuid4())},method="POST")
 return json.load(urllib.request.urlopen(req))
for order,(name,summary) in enumerate(projects):
 p=post("/api/projects",{"name":name,"summary":summary,"location":f"synthetic/{name.lower().replace(' ','-')}","display_order":order,"actor":"seed"})
 post(f"/api/projects/{p['id']}/tasks",{"title":"다음 검증 단계 실행","actor":"seed","state":"needs_review" if order in (2,4) else "todo"})
 post(f"/api/projects/{p['id']}/notes",{"text":"합성 데모 데이터입니다.","author":"seed"})
print("Seeded 7 synthetic projects")
