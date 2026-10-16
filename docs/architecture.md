# Architecture and contracts

Status: 0.1 vertical slice implemented; remaining gaps are tracked in the README.

## Implemented stack decision

- **Python 3.11+, FastAPI, Uvicorn** keep the authenticated HTTP contract small, typed, and easy to operate as one systemd process. The CLI deliberately uses Python's standard HTTP library, so installing the service also installs a client without another runtime.
- **SQLite (WAL)** fits a personal seven-project workspace, provides transactions for entity plus activity writes, portable backup, and durable state without another daemon. A write transaction also serializes revision and idempotency checks. A future multi-user/high-write release should reassess PostgreSQL.
- **Framework-free HTML/CSS/JavaScript** keeps the dashboard and compact route one deployable artifact. It polls an authenticated snapshot every three seconds; this is live refresh without page reload, though push synchronization remains roadmap work.
- **pywebview (optional)** reuses the responsive dashboard in a small always-on-top Windows window instead of maintaining a second UI. Native Windows behavior remains unverified on Linux.

## Boundaries

One central service owns persisted state and exposes an authenticated API. The web application, desktop widget, and CLI use this API. Desktop and web interfaces should reuse presentation components where practical.

The service runs on an always-on host reachable over Tailscale. A project location is metadata (local path or SSH host alias plus remote path), not authority to execute commands on that host. No source-code ingestion is required.

## Entities

- Project: stable ID, name, location, lifecycle state, current summary, display order, revision, update time.
- Task: stable ID, project ID, title, details, state, priority, actor, blocking reason, revision.
- Note: stable ID, project ID, text, author, revision.
- Activity: stable ID, project ID, related entity ID, event type, actor label, authenticated client ID, occurrence time, receipt time, summary.

Store timestamps in UTC; render and filter dates in the user's timezone. Use server receipt ordering as a deterministic fallback when client clocks differ. Preserve the submitted occurrence time without claiming remote clocks are authoritative.

## Mutation guarantees

- Commit entity changes and their corresponding activity atomically.
- Use expected revisions for updates; reject stale writes with a conflict response.
- Accept idempotency keys for retried mutations, scoped to the authenticated client. Reusing a key with a different payload must fail.
- Keep human notes separate from replaceable status summaries.
- Persist history and support explicit corrections instead of silently rewriting past events.
- Use authenticated clients with revocable credentials; actor labels are descriptive, not an authorization mechanism.

## Synchronization and offline behavior

Clients fetch a current snapshot and subscribe to changes. Reconnection must recover missed changes or refresh the snapshot. The UI shows last successful synchronization and stale state.

The CLI may queue mutations locally during outages. A queued operation is reported as pending, not committed. Replaying a queue preserves event IDs and occurrence times. Revision conflicts stop the affected update and expose resolution instructions; they must not overwrite newer server state. Initial delivery can use explicit queue flushing, provided the behavior is documented.

## Deployment acceptance

Provide a reproducible server install, persistent data directory, health check, authentication setup, and backup/restore instructions. Keep credentials out of project repositories and process arguments where possible. Tailscale is the transport boundary; service authentication is still required.

Choose the runtime, persistence engine, web framework, and desktop wrapper during implementation. Record material choices with reasons and runnable validation rather than treating this proposal as an implemented system.
