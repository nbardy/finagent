from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPO_CODEX_HOME = REPO_ROOT / ".codex"
GLOBAL_CODEX_HOME = Path(os.environ.get("HOME", str(Path.home()))) / ".codex"
GLOBAL_SKILLS = GLOBAL_CODEX_HOME / "skills"
SHARED_SKILL_DIRS = [".system", "public", "playwright"]


def ensure_symlink(src: Path, dst: Path, *, force: bool = False) -> None:
    if dst.is_symlink():
        if dst.resolve() == src.resolve():
            return
        if not force:
            raise SystemExit(f"{dst} already points elsewhere: {dst.resolve()}")
        dst.unlink()
    elif dst.exists():
        if not force:
            raise SystemExit(f"{dst} already exists; use --force to replace")
        if dst.is_dir():
            shutil.rmtree(dst)
        else:
            dst.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.symlink_to(src)


def ensure_config(repo_codex_home: Path, *, force: bool = False) -> None:
    src = GLOBAL_CODEX_HOME / "config.toml"
    dst = repo_codex_home / "config.toml"
    if dst.exists() and not force:
        return
    if dst.exists():
        dst.unlink()
    if src.exists():
        shutil.copy2(src, dst)


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare a repo-local CODEX_HOME")
    parser.add_argument("--dest", type=Path, default=DEFAULT_REPO_CODEX_HOME)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo_codex_home = args.dest
    skills_root = repo_codex_home / "skills"
    skills_root.mkdir(parents=True, exist_ok=True)

    ensure_config(repo_codex_home, force=args.force)

    for name in SHARED_SKILL_DIRS:
        src = GLOBAL_SKILLS / name
        if src.exists():
            ensure_symlink(src, skills_root / name, force=args.force)

    print(f"Prepared repo-local CODEX_HOME at {repo_codex_home}")
    print(f"Launch with: CODEX_HOME={repo_codex_home} codex -C {REPO_ROOT}")


if __name__ == "__main__":
    main()
