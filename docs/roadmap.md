# Delivery roadmap

An initial runnable vertical slice now spans all five stages. It is not a completed release: see the README's explicit remaining acceptance gaps. The stages below remain the direction for hardening.

## 1. Central service and persistence

Select and document the stack. Implement projects, tasks, notes, activity, authentication, atomic mutations, revision checks, and idempotency. Validate persistence across restarts, unauthorized access, conflicts, and duplicate requests.

## 2. CLI and project registration

Implement server configuration, credential handling, folder-to-project mapping, human-readable and JSON output, and project/task/note commands. Validate a local client and a client on a Tailscale-connected server. Add an explicit offline queue and replay behavior.

## 3. Web dashboard

Build the compact seven-project list, expandable details, editing, attention filters, and chronological history. Add live synchronization, timezone-aware date filters, and disconnected state. Verify keyboard access and narrow/wide layouts with synthetic data.

## 4. Windows desktop widget

Reuse the dashboard in a small desktop window with always-on-top support and links to full web details. Verify window behavior on Windows and state synchronization with the web UI.

## 5. Agent skills and self-hosted release

Ship Codex and Claude Code instructions using the actual CLI contract. Validate read-before-work, start/progress/block/complete reporting, and preservation of human notes. Publish server setup, upgrade, backup, recovery, and client setup instructions. Run the complete acceptance scenario from the product specification before tagging a release.
