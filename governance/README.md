# Governance Bootstrap Toolkit

This folder contains a reusable scaffolder for the 7-file governance framework.

## What it creates

1. `active_context.md`
2. `docs/contracts.md`
3. `docs/agent_core.md`
4. `docs/agent_project.md`
5. `docs/decisions.md`
6. `docs/build_plan.md`
7. `docs/state.md`

## Quick start

From this repository root:

```powershell
python governance/bootstrap_governance.py \
  --target "C:\path\to\your-project" \
  --project "My Project" \
  --module "Module 0" \
  --task "Set initial scope"
```

## PowerShell wrapper

```powershell
.\governance\init-governance.ps1 \
  -TargetPath "C:\path\to\your-project" \
  -ProjectName "My Project" \
  -CurrentModule "Module 0" \
  -CurrentTask "Set initial scope"
```

## Useful flags

- `--dry-run` prints planned actions only.
- `--force` overwrites existing files.

## Recommended usage pattern

1. Run the scaffolder at project start.
2. Update `active_context.md` before each session.
3. Update `docs/state.md` after each session.
4. Add entries to `docs/decisions.md` when making non-obvious decisions.
