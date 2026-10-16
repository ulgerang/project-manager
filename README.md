# Project Manager

자기 호스팅 가능한 프로젝트 현황 서비스, 반응형 웹 대시보드, 에이전트용 `pmw` CLI의 **실행 가능한 0.1 수직 슬라이스**입니다. SQLite에 프로젝트·작업·메모·활동을 함께 보존하며 웹은 3초 간격으로 자동 동기화합니다.

## 빠른 시작

Python 3.11 이상이 필요합니다.

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[test]'
export PMW_TOKEN='local-demo-token' PMW_DB="$PWD/data/pmw.db"
pmw-server
```

다른 터미널에서 합성 데이터만 넣고 `http://127.0.0.1:8765`를 열어 같은 토큰으로 연결합니다.

```bash
PMW_TOKEN=local-demo-token python scripts/seed.py
pmw config http://127.0.0.1:8765 --token local-demo-token
pmw --json init --name 'My project' --location "$PWD"
pmw map set PROJECT_ID --folder "$PWD"
pmw --json status
```

전역 옵션 `--json`과 `--project`는 하위 명령 앞에 둡니다. `pmw --help`가 실제 계약입니다. 변경 명령은 최신 `revision`을 요구하고 충돌을 덮어쓰지 않습니다. 연결 실패 시 기본값은 실패입니다. `--queue`를 명시한 변경만 `~/.config/pmw/queue.jsonl`에 **pending**으로 저장되며 `pmw queue flush`로 순서대로 재전송합니다. 첫 충돌/서버 오류에서 멈추며 중복은 동일 idempotency key로 제거됩니다.

## 운영 설치

1. 전용 `pmw` 사용자와 `/opt/project-manager/.venv` 가상환경을 만들고 이 패키지를 설치합니다. `/var/lib/pmw`는 `pmw` 소유로 생성합니다.
2. `.env.example`을 `/etc/project-manager.env`로 복사하고 권한을 `0600`으로 설정합니다. 긴 무작위 토큰과 `/var/lib/pmw/pmw.db`를 지정합니다.
3. `deploy/pmw.service`를 `/etc/systemd/system/project-manager.service`로 복사하고 `systemctl enable --now project-manager`로 활성화합니다.
4. `curl http://127.0.0.1:8765/health`로 확인합니다. Tailscale 주소에 직접 노출하거나 해당 네트워크 안의 TLS reverse proxy를 사용하되 서비스 토큰도 유지합니다. 이 저장소는 Tailscale 등록/공개 인터넷 배포를 수행하지 않습니다.

### 백업과 복원

일관된 온라인 백업은 SQLite CLI를 이용합니다.

```bash
mkdir -p backups
sqlite3 data/pmw.db ".backup 'backups/pmw-$(date +%F).db'"
sqlite3 backups/pmw-2026-10-16.db 'PRAGMA integrity_check'
```

복원할 때 서비스를 중지하고 현재 DB와 `-wal`/`-shm` 파일을 별도 보관한 뒤 검증한 백업 파일을 `PMW_DB` 위치로 복사하여 소유권을 복구하고 재시작합니다. `/health` 및 인증된 `/api/snapshot`을 확인합니다. 스키마는 현재 시작 시 멱등 생성되며 0.1에는 별도 버전 마이그레이션 도구가 없습니다.

## Windows 위젯

`pip install -e '.[desktop]'` 후 `pmw config SERVER_URL --token TOKEN`으로 연결하고 `pmw-widget`을 실행합니다. 기존 설정 파일이 있으면 서버 URL과 토큰을 직접 편집해 토큰을 명령 이력에 남기지 않을 수 있습니다. WebView2 런타임이 필요합니다. pywebview 창은 460×640, always-on-top으로 `/widget?compact=1`을 재사용합니다. 저장된 CLI 인증은 같은 서버 origin의 위젯에만 전달합니다. 서버를 바꾸려면 CLI 설정도 바꾸세요.

Windows 설치 시에는 가상환경을 사용자 프로그램 폴더에 유지하고 `pythonw.exe`로 `pmw.widget.main()`을 실행하는 바로가기를 만들 수 있습니다. 자동 실행이 필요하면 그 바로가기를 Windows 시작프로그램 폴더에 복사합니다. 초기 설치 검증에서 실제 Windows 창, 자동 인증, always-on-top 및 Tailscale 연결을 확인했습니다. 배포용 서명 설치 프로그램은 아직 없습니다.

## AI 스킬

`skills/codex/SKILL.md`를 `~/.codex/skills/project-manager-reporting/SKILL.md`에, Claude Code 버전은 `~/.claude/skills/project-manager-reporting/SKILL.md`에 설치합니다. SSH 서버에서 AI를 실행한다면 해당 서버에도 CLI 설정과 스킬을 설치하세요. 새 세션에서 스킬을 불러오고, 프로젝트 폴더를 `pmw map set PROJECT_ID`로 연결합니다. 서버 주소와 토큰은 스킬에 넣지 않습니다.

## 검증

```bash
pytest -q
```

테스트는 임시 SQLite DB로 인증 실패, 원자적 엔터티/이력 변경, 재전송 중복 제거, 충돌, 재시작 지속성과 오프라인 큐의 명시적 pending 표시를 검사합니다.

## 현재 범위와 남은 차이

구현됨: 프로젝트 등록/요약, 작업 생성·상태 변경, 보존 메모, 발생/수신 시각과 작성자/인증 클라이언트가 있는 활동, 날짜·프로젝트 조회, 고정 순서 7행 UI, 여러 상세 펼침, 확인 필요 필터, 폴링 동기화, 폴더 매핑, JSON CLI, 명시적 큐/재생, compact 웹과 Windows wrapper.

남음: 웹의 프로젝트/작업 전체 편집과 drag reorder, 토큰 발급·폐기 관리 UI, SSE/WebSocket(현재 polling), 활동 정정 API, 정식 스키마 migration, 설치 패키지/Windows 서명. 작업 상태는 실행 신호가 아니며 0.1은 별도 agent heartbeat를 아직 제공하지 않습니다. Windows/Tailscale 설치 검증은 특정 설치 환경의 확인이며 모든 플랫폼 조합의 검증을 뜻하지 않습니다.

설계 근거는 [architecture](docs/architecture.md), 수용 기준은 [제품 기획](docs/product-spec.ko.md), 단계는 [roadmap](docs/roadmap.md)을 참조하세요.
