# Initial Codex Cloud implementation task

Implement the first runnable end-to-end version of Project Manager from this repository's product specification. Read AGENTS.md and docs/product-spec.ko.md, docs/architecture.md, and docs/roadmap.md first.

Choose a maintainable stack and record the rationale. Prioritize a working central service, CLI, and responsive web UI that share persisted data. Include project registration, current summaries, tasks, notes, attributed chronological activity, authentication, optimistic concurrency, atomic history updates, and idempotent retries. Support seven synthetic projects as compact rows with expandable details, date filters, and live synchronization. Provide a compact widget view and a Windows desktop wrapper if feasible; report native verification as pending when unavailable.

Implement the actual CLI before writing Codex and Claude Code skill instructions against it. Include JSON output and folder mappings. Provide explicit offline queuing/replay or clearly mark any remaining work. Do not silently present pending operations as successful writes.

Add reproducible setup, disposable tests, CI, server deployment instructions, and backup/restore documentation appropriate to the implemented scope. Verify backend/CLI behavior and exercise the web UI with synthetic data. Correct failures before delivery. Do not use real credentials, private servers, project data, or Tailscale enrollment keys. Do not deploy to a production server.

Produce a reviewable change and a Korean handoff explaining implemented behavior, validation, and remaining acceptance gaps. Do not claim Windows or real remote-network verification from a Linux-only environment. Keep the README status accurate. If the full first version does not fit one run, finish a coherent runnable vertical slice and explicitly list remaining roadmap items.
