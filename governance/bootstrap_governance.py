"""Scaffold the 7-file governance framework into any project folder.

Usage example:
    python governance/bootstrap_governance.py \
      --target "C:\\path\\to\\project" \
      --project "My Project" \
      --module "Module 0" \
      --task "Initial setup"
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class RenderContext:
    project_name: str
    today: str
    current_module: str
    current_task: str


def _render_template(text: str, ctx: RenderContext) -> str:
    replacements = {
        "{{PROJECT_NAME}}": ctx.project_name,
        "{{TODAY}}": ctx.today,
        "{{CURRENT_MODULE}}": ctx.current_module,
        "{{CURRENT_TASK}}": ctx.current_task,
    }
    rendered = text
    for key, value in replacements.items():
        rendered = rendered.replace(key, value)
    return rendered


def _write_file(
    source_path: Path,
    target_path: Path,
    ctx: RenderContext,
    *,
    force: bool,
    dry_run: bool,
) -> str:
    if target_path.exists() and not force:
        return f"skip   {target_path} (already exists)"

    action = "write"
    if target_path.exists() and force:
        action = "overwrite"

    if dry_run:
        return f"{action:<7}{target_path}"

    target_path.parent.mkdir(parents=True, exist_ok=True)
    template_text = source_path.read_text(encoding="utf-8")
    rendered = _render_template(template_text, ctx)
    target_path.write_text(rendered, encoding="utf-8")
    return f"{action:<7}{target_path}"


def _iter_template_files(template_root: Path) -> list[Path]:
    return sorted(p for p in template_root.rglob("*.md") if p.is_file())


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap the 7-file governance framework into a target project.",
    )
    parser.add_argument("--target", required=True, help="Target project directory.")
    parser.add_argument("--project", required=True, help="Project display name.")
    parser.add_argument(
        "--module",
        default="Module 0",
        help="Initial current module for active_context/state.",
    )
    parser.add_argument(
        "--task",
        default="Set session scope",
        help="Initial current task for active_context.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing governance files.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview actions without writing files.",
    )

    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    template_root = script_dir / "templates"
    target_root = Path(args.target).expanduser().resolve()

    if not template_root.exists():
        raise FileNotFoundError(f"Template root not found: {template_root}")

    ctx = RenderContext(
        project_name=args.project,
        today=date.today().isoformat(),
        current_module=args.module,
        current_task=args.task,
    )

    template_files = _iter_template_files(template_root)
    if not template_files:
        raise RuntimeError("No template files found.")

    print(f"Target project: {target_root}")
    print(f"Project name : {ctx.project_name}")
    print(f"Dry run      : {args.dry_run}")
    print(f"Force        : {args.force}")
    print()

    for source_path in template_files:
        rel = source_path.relative_to(template_root)
        target_path = target_root / rel
        result = _write_file(
            source_path,
            target_path,
            ctx,
            force=args.force,
            dry_run=args.dry_run,
        )
        print(result)

    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
