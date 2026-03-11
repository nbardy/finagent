from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PRIVATE_SKILLS_DIR = REPO_ROOT / ".codex" / "skills"
DEFAULT_DEST = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")) / "skills"
SKIP_DIRS = {".system", "public", "playwright"}


@dataclass(frozen=True)
class RepoSkill:
    folder_name: str
    path: Path
    skill_name: str


def parse_skill_name(skill_md: Path) -> str:
    lines = skill_md.read_text().splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{skill_md} missing frontmatter")
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if line.startswith("name:"):
            return line.split(":", 1)[1].strip()
    raise ValueError(f"{skill_md} missing skill name")


def discover_repo_skills() -> list[RepoSkill]:
    skills: list[RepoSkill] = []
    if not PRIVATE_SKILLS_DIR.exists():
        return skills
    for skill_dir in sorted(PRIVATE_SKILLS_DIR.iterdir()):
        if not skill_dir.is_dir():
            continue
        if skill_dir.name in SKIP_DIRS:
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        skills.append(
            RepoSkill(
                folder_name=skill_dir.name,
                path=skill_dir,
                skill_name=parse_skill_name(skill_md),
            )
        )
    return skills


def select_skills(repo_skills: list[RepoSkill], names: list[str], install_all: bool) -> list[RepoSkill]:
    if install_all:
        return repo_skills
    if not names:
        raise SystemExit("Pass skill names or use --all")
    wanted = set(names)
    selected = [
        skill
        for skill in repo_skills
        if skill.folder_name in wanted or skill.skill_name in wanted
    ]
    if len(selected) != len(wanted):
        found = {skill.folder_name for skill in selected} | {skill.skill_name for skill in selected}
        missing = sorted(wanted - found)
        raise SystemExit(f"Unknown skills: {', '.join(missing)}")
    return selected


def print_status(repo_skills: list[RepoSkill], dest_root: Path) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    for skill in repo_skills:
        dest = dest_root / skill.folder_name
        if dest.is_symlink():
            target = dest.resolve()
            status = "linked" if target == skill.path.resolve() else f"linked-> {target}"
        elif dest.exists():
            status = "exists (not symlink)"
        else:
            status = "missing"
        print(f"{skill.folder_name:<24} name={skill.skill_name:<20} status={status}")


def install_skills(skills: list[RepoSkill], dest_root: Path, force: bool) -> None:
    dest_root.mkdir(parents=True, exist_ok=True)
    for skill in skills:
        dest = dest_root / skill.folder_name
        if dest.is_symlink():
            current_target = dest.resolve()
            if current_target == skill.path.resolve():
                print(f"already linked: {dest} -> {current_target}")
                continue
            if not force:
                raise SystemExit(f"{dest} already points to {current_target}; use --force to replace")
            dest.unlink()
        elif dest.exists():
            if not force:
                raise SystemExit(f"{dest} already exists; use --force to replace")
            if dest.is_dir():
                shutil.rmtree(dest)
            else:
                dest.unlink()
        dest.symlink_to(skill.path)
        print(f"linked: {dest} -> {skill.path}")
    print("Restart Codex to pick up new skills.")


def uninstall_skills(skills: list[RepoSkill], dest_root: Path) -> None:
    for skill in skills:
        dest = dest_root / skill.folder_name
        if dest.is_symlink() or dest.exists():
            if dest.is_dir() and not dest.is_symlink():
                raise SystemExit(f"{dest} is a real directory, not a symlink; refusing to remove")
            dest.unlink()
            print(f"removed: {dest}")
        else:
            print(f"missing: {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Install repo-local Codex skills via symlink")
    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)

    install_parser = subparsers.add_parser("install")
    install_parser.add_argument("skills", nargs="*")
    install_parser.add_argument("--all", action="store_true")
    install_parser.add_argument("--force", action="store_true")
    install_parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)

    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("skills", nargs="*")
    uninstall_parser.add_argument("--all", action="store_true")
    uninstall_parser.add_argument("--dest", type=Path, default=DEFAULT_DEST)

    args = parser.parse_args()
    repo_skills = discover_repo_skills()

    if args.command == "status":
        print_status(repo_skills, args.dest)
        return

    selected = select_skills(repo_skills, getattr(args, "skills", []), getattr(args, "all", False))
    if args.command == "install":
        install_skills(selected, args.dest, args.force)
        return
    if args.command == "uninstall":
        uninstall_skills(selected, args.dest)
        return

    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
