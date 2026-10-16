# Project Manager

A self-hosted project dashboard for people working with AI coding agents.

See what is happening across your projects, what needs your attention, and what to do next. Manage the same information through a web dashboard, a desktop widget, or a CLI used by Codex and Claude Code.

**Status: planning and repository setup. No runnable application is available yet.**

## Planned experience

- A compact desktop widget with one row per project and expandable details.
- A full web dashboard for tasks, notes, and chronological activity.
- A central server reachable over your Tailscale network.
- A CLI for local and SSH-hosted projects.
- Agent skills for reading tasks and reporting meaningful progress.
- Shared state for human and agent updates, with attribution and history.

The initial target is a personal workspace with approximately seven projects. Adding a task does not automatically launch an agent.

## Architecture

```text
Local agents -------- CLI ----+
                             +---- Central service + database
Remote agents ------- CLI ----+              |
                                     Web dashboard
                                     Desktop widget
```

The service runs on an always-on server. Clients connect over Tailscale and authenticate to the service. Project source code stays on its original machine; the service stores project metadata, tasks, notes, and activity.

## Project documents

- [Product specification (Korean)](docs/product-spec.ko.md)
- [Architecture and data contracts](docs/architecture.md)
- [Delivery roadmap](docs/roadmap.md)
- [Contributing](CONTRIBUTING.md)
- [Security policy](SECURITY.md)

Implementation choices will be documented as development begins. Examples in the specification describe intended behavior, not currently available commands.

## License

[MIT](LICENSE)
