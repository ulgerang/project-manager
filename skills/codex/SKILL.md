---
name: project-manager-reporting
description: Read and update a registered project's Project Manager status, tasks, and activity through the pmw CLI while working on that project.
---

# Project Manager reporting

Use the mapped project folder or put `--project PROJECT_ID` before the subcommand. Global options precede subcommands: `pmw --json status`, `pmw --json task list`, and `pmw --json note list`.

Read the current status, tasks, and notes before project work. If the folder is not registered, report that setup gap; do not register arbitrary projects automatically. Only report changes within the user's authorized project work.

Report meaningful boundaries with `--actor codex`: work start, progress, blockers, and completion. Use `pmw status-set TEXT --revision N --actor codex` for a project summary. Use `pmw task start ID --revision N --actor codex`, `pmw task done ID --revision N --actor codex --summary TEXT`, or `pmw task block ID --revision N --actor codex --reason TEXT` for tasks. Project and task revisions are separate; read the latest entity revision and reconcile conflicts rather than overwriting another update. Quote prose arguments for the current shell.

Never replace human notes or imply a task state proves an agent is running. Failed writes are not successful reports. Use `--queue` only when pending delivery is acceptable, label it pending, and use `pmw queue flush` to retry. Verify the resulting status after replay; a remaining queue may require conflict resolution.
