# Working on Project Manager

Read `docs/product-spec.ko.md`, `docs/architecture.md`, and `docs/roadmap.md` before implementation. The product specification is the acceptance source; the roadmap describes delivery stages.

- Build a self-hosted service, web dashboard, compact Windows widget, and agent-facing CLI around shared persisted data.
- Preserve atomic status/history updates, attribution, optimistic concurrency, idempotency, and human-authored notes.
- Do not infer running agent status from a task's progress state.
- Use synthetic data for development and screenshots. Do not connect to private servers or publish real project inventories.
- Keep credentials and runtime databases out of Git. Use environment examples with placeholders.
- Document stack choices, setup, migrations, and reproducible validation as code is introduced.
- Validate behavior with disposable resources. Include authentication, persistence, replay, and conflict tests when those features are implemented.
- Verify UI changes in a browser when available. Record unverified native Windows or real Tailscale checks honestly; Linux CI cannot establish those results.
- Deliver focused, reviewable changes. Do not deploy to production or claim unimplemented milestones are complete.
- Report results to the project owner in Korean; public code and API identifiers may use English.
