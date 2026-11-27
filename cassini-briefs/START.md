# Start on Lava (WSL)
Copy these seven Markdown files into a new repo (or an empty existing repo). From that directory:
```bash
git init -b main
git add *.md
git commit -m 'Freeze EIP hackathon brief and contract v0.1'
git worktree add ../cassini-data -b data
git worktree add ../cassini-core -b core
git worktree add ../cassini-ui -b ui
```
In separate terminals, enter each worktree and launch the installed coding agent (`claude`, `codex`, `agy` respectively). If a command is unavailable, use another installed agent or its supported interface. Prompt each: `Read AGENTS.md, PRD.md, CONTRACT.md and [your brief]. Implement only your workstream, test, commit and report blockers.`

Human integrator: check branch diffs, run tests, merge one branch at a time into main, resolve conflicts and rerun full integration. Never merge unchecked work. Confirm solo eligibility, AI use and deadline with organisers. Verify data endpoints and rights before retrieval; links in PRD are starting points, not revalidated in this document creation turn. No actual code or datasets are delivered in this pack.
