---
name: project-manager-reporting
description: Read and update a registered project's Project Manager status, tasks, and activity through the pmw CLI while working on that project.
---

# Project Manager reporting

Use the mapped project folder or put `--project PROJECT_ID` before the subcommand. Global options precede subcommands: `pmw --json status`, `pmw --json task list`, and `pmw --json note list`.

Read status, tasks, and notes before project work. If the folder is unregistered, report the setup gap instead of registering arbitrary projects. Reporting is limited to the user's authorized project work.

Report work start, meaningful progress, blockers, and completion. Use `pmw status-set TEXT --revision N --actor claude-code`; use `pmw task start ID --revision N --actor claude-code`, `pmw task done ID --revision N --actor claude-code --summary TEXT`, or `pmw task block ID --revision N --actor claude-code --reason TEXT`. Read the corresponding project or task revision before updates. Reconcile conflicts rather than overwriting newer state. Quote prose for the current shell.

Preserve human notes. Task progress does not prove that an agent is running. Writes fail without connectivity unless `--queue` is explicit; report queued writes as pending, replay with `pmw queue flush`, and verify the resulting status. Remaining queued operations can require conflict resolution.
