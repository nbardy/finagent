from __future__ import annotations

import argparse
import json
import re
import subprocess
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = REPO_ROOT / "research_sessions"


@dataclass
class CodexTurnResult:
    thread_id: str
    prompt: str
    last_message: str
    stderr: str
    exit_code: int
    events: list[dict[str, Any]]


@dataclass
class LatestTweetResult:
    username: str
    found: bool
    source_url: str | None
    posted_at: str | None
    text: str | None
    summary: str | None
    caveats: list[str]
    thread_id: str | None


@dataclass
class ResearchSessionPaths:
    session_dir: Path
    loose_notes_dir: Path
    documents_dir: Path
    statements_dir: Path
    filings_dir: Path
    articles_dir: Path
    analysis_dir: Path
    conclusions_dir: Path
    final_report_path: Path
    manifest_path: Path


@dataclass
class ResearchSessionResult:
    topic: str
    session_dir: Path
    thread_id: str | None
    latest_tweet: LatestTweetResult | None
    turns: list[CodexTurnResult]


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "research-session"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_slug(now: datetime | None = None) -> str:
    current = now or _utc_now()
    return current.strftime("%Y-%m-%d_%H%M%S")


def _session_name(topic: str, ticker: str | None = None, now: datetime | None = None) -> str:
    label = ticker or topic
    return f"{_timestamp_slug(now)}_{_slugify(label)}"


def _ensure_session_layout(
    topic: str,
    ticker: str | None = None,
    root: Path = RESEARCH_ROOT,
    now: datetime | None = None,
) -> ResearchSessionPaths:
    session_dir = root / _session_name(topic=topic, ticker=ticker, now=now)
    loose_notes_dir = session_dir / "loose_notes"
    documents_dir = session_dir / "documents"
    statements_dir = documents_dir / "statements"
    filings_dir = documents_dir / "filings"
    articles_dir = documents_dir / "articles"
    analysis_dir = session_dir / "analysis"
    conclusions_dir = session_dir / "conclusions"
    final_report_path = session_dir / "final_report.md"
    manifest_path = session_dir / "session.json"

    for path in (
        loose_notes_dir,
        statements_dir,
        filings_dir,
        articles_dir,
        analysis_dir,
        conclusions_dir,
    ):
        path.mkdir(parents=True, exist_ok=True)

    if not final_report_path.exists():
        final_report_path.write_text(
            "# Final Report\n\nCodex research has not finished yet.\n",
            encoding="utf-8",
        )

    return ResearchSessionPaths(
        session_dir=session_dir,
        loose_notes_dir=loose_notes_dir,
        documents_dir=documents_dir,
        statements_dir=statements_dir,
        filings_dir=filings_dir,
        articles_dir=articles_dir,
        analysis_dir=analysis_dir,
        conclusions_dir=conclusions_dir,
        final_report_path=final_report_path,
        manifest_path=manifest_path,
    )


def _write_manifest(
    paths: ResearchSessionPaths,
    *,
    topic: str,
    ticker: str | None,
    x_username: str | None,
    thread_id: str | None,
    turns: list[CodexTurnResult],
    latest_tweet: LatestTweetResult | None,
) -> None:
    manifest = {
        "topic": topic,
        "ticker": ticker,
        "x_username": x_username,
        "thread_id": thread_id,
        "updated_at": _utc_now().isoformat(timespec="seconds"),
        "paths": {
            "session_dir": str(paths.session_dir),
            "loose_notes_dir": str(paths.loose_notes_dir),
            "documents_dir": str(paths.documents_dir),
            "analysis_dir": str(paths.analysis_dir),
            "conclusions_dir": str(paths.conclusions_dir),
            "final_report_path": str(paths.final_report_path),
        },
        "turns": [
            {
                "thread_id": turn.thread_id,
                "prompt": turn.prompt,
                "exit_code": turn.exit_code,
                "stderr": turn.stderr,
                "last_message": turn.last_message,
            }
            for turn in turns
        ],
        "latest_tweet": asdict(latest_tweet) if latest_tweet else None,
    }
    paths.manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def _write_request_brief(
    paths: ResearchSessionPaths,
    *,
    topic: str,
    ticker: str | None,
    x_username: str | None,
) -> None:
    brief = [
        f"# Research Brief: {topic}",
        "",
        f"- Created: {_utc_now().isoformat(timespec='seconds')}",
        f"- Topic: {topic}",
        f"- Ticker: {ticker or 'n/a'}",
        f"- X/Twitter user: {x_username or 'n/a'}",
        "",
        "Expected outputs:",
        "- `loose_notes/` for raw scratch notes",
        "- `documents/statements/` for company statements and transcripts",
        "- `documents/filings/` for filings and formal disclosures",
        "- `documents/articles/` for articles and web captures",
        "- `analysis/` for analytical markdown",
        "- `conclusions/` for concise decision memos",
        "- `final_report.md` for the final synthesis",
        "",
    ]
    (paths.loose_notes_dir / "request_brief.md").write_text(
        "\n".join(brief),
        encoding="utf-8",
    )


def _build_command(
    *,
    prompt: str,
    repo_root: Path,
    profile: str | None,
    output_schema_path: Path | None,
    output_message_path: Path,
    resume_thread_id: str | None,
    full_auto: bool,
    dangerously_bypass: bool,
) -> list[str]:
    base = ["codex", "exec"]
    if resume_thread_id:
        base.extend(["resume", resume_thread_id])
    else:
        base.extend(["-C", str(repo_root)])

    if full_auto:
        base.append("--full-auto")
    if dangerously_bypass:
        base.append("--dangerously-bypass-approvals-and-sandbox")

    base.extend(["--json", "-o", str(output_message_path)])
    if profile:
        base.extend(["-p", profile])
    if output_schema_path:
        base.extend(["--output-schema", str(output_schema_path)])
    base.append(prompt)
    return base


def _run_codex_turn(
    *,
    prompt: str,
    repo_root: Path = REPO_ROOT,
    profile: str | None = None,
    output_schema: dict[str, Any] | None = None,
    resume_thread_id: str | None = None,
    full_auto: bool = True,
    dangerously_bypass: bool = False,
) -> CodexTurnResult:
    with tempfile.TemporaryDirectory(prefix="finagent_codex_") as tmp_dir:
        tmp_path = Path(tmp_dir)
        output_message_path = tmp_path / "last_message.txt"
        output_schema_path = tmp_path / "schema.json" if output_schema else None

        if output_schema_path:
            output_schema_path.write_text(
                json.dumps(output_schema, indent=2),
                encoding="utf-8",
            )

        command = _build_command(
            prompt=prompt,
            repo_root=repo_root,
            profile=profile,
            output_schema_path=output_schema_path,
            output_message_path=output_message_path,
            resume_thread_id=resume_thread_id,
            full_auto=full_auto,
            dangerously_bypass=dangerously_bypass,
        )

        process = subprocess.Popen(
            command,
            cwd=repo_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        events: list[dict[str, Any]] = []
        thread_id = resume_thread_id

        assert process.stdout is not None
        for raw_line in process.stdout:
            line = raw_line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                event = {"type": "raw", "text": line}
            events.append(event)
            if event.get("type") == "thread.started":
                thread_id = event.get("thread_id", thread_id)

        stderr = ""
        if process.stderr is not None:
            stderr = process.stderr.read().strip()
        exit_code = process.wait()

        last_message = ""
        if output_message_path.exists():
            last_message = output_message_path.read_text(encoding="utf-8").strip()

        if exit_code != 0:
            raise RuntimeError(
                "Codex research turn failed.\n"
                f"command={' '.join(command)}\n"
                f"exit_code={exit_code}\n"
                f"stderr={stderr or 'n/a'}\n"
                f"last_message={last_message or 'n/a'}"
            )

        if not thread_id:
            raise RuntimeError("Codex turn completed without a thread id.")

        return CodexTurnResult(
            thread_id=thread_id,
            prompt=prompt,
            last_message=last_message,
            stderr=stderr,
            exit_code=exit_code,
            events=events,
        )


def get_users_latest_tweet(
    username: str,
    *,
    repo_root: Path = REPO_ROOT,
    profile: str | None = None,
    full_auto: bool = True,
    dangerously_bypass: bool = False,
    output_dir: Path | None = None,
) -> LatestTweetResult:
    schema = {
        "type": "object",
        "required": [
            "found",
            "username",
            "source_url",
            "posted_at",
            "text",
            "summary",
            "caveats",
        ],
        "properties": {
            "found": {"type": "boolean"},
            "username": {"type": "string"},
            "source_url": {"type": ["string", "null"]},
            "posted_at": {"type": ["string", "null"]},
            "text": {"type": ["string", "null"]},
            "summary": {"type": ["string", "null"]},
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    }

    prompt = "\n".join(
        [
            f"Find the latest public X/Twitter post from @{username}.",
            "Use browsing if needed.",
            "Return JSON only under the provided schema.",
            "If you cannot verify the latest post, set found=false and explain the uncertainty in caveats.",
            "Keep the summary concise and factual.",
        ]
    )

    turn = _run_codex_turn(
        prompt=prompt,
        repo_root=repo_root,
        profile=profile,
        output_schema=schema,
        full_auto=full_auto,
        dangerously_bypass=dangerously_bypass,
    )
    data = json.loads(turn.last_message)
    result = LatestTweetResult(
        username=data["username"],
        found=data["found"],
        source_url=data["source_url"],
        posted_at=data["posted_at"],
        text=data["text"],
        summary=data["summary"],
        caveats=list(data["caveats"]),
        thread_id=turn.thread_id,
    )

    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "latest_tweet.json").write_text(
            json.dumps(asdict(result), indent=2),
            encoding="utf-8",
        )
        markdown_lines = [
            f"# Latest Post: @{username}",
            "",
            f"- Found: {result.found}",
            f"- Thread ID: {result.thread_id or 'n/a'}",
            f"- Source: {result.source_url or 'n/a'}",
            f"- Posted at: {result.posted_at or 'n/a'}",
            "",
            "## Text",
            "",
            result.text or "Unavailable.",
            "",
            "## Summary",
            "",
            result.summary or "Unavailable.",
        ]
        if result.caveats:
            markdown_lines.extend(["", "## Caveats", ""])
            markdown_lines.extend(f"- {caveat}" for caveat in result.caveats)
        (output_dir / "latest_tweet.md").write_text(
            "\n".join(markdown_lines),
            encoding="utf-8",
        )

    return result


def do_research(
    topic: str,
    *,
    ticker: str | None = None,
    x_username: str | None = None,
    repo_root: Path = REPO_ROOT,
    profile: str | None = None,
    full_auto: bool = True,
    dangerously_bypass: bool = False,
    dry_run: bool = False,
) -> ResearchSessionResult:
    paths = _ensure_session_layout(topic=topic, ticker=ticker)
    _write_request_brief(paths, topic=topic, ticker=ticker, x_username=x_username)

    latest_tweet: LatestTweetResult | None = None
    turns: list[CodexTurnResult] = []

    if x_username and not dry_run:
        latest_tweet = get_users_latest_tweet(
            x_username,
            repo_root=repo_root,
            profile=profile,
            full_auto=full_auto,
            dangerously_bypass=dangerously_bypass,
            output_dir=paths.loose_notes_dir,
        )

    if dry_run:
        _write_manifest(
            paths,
            topic=topic,
            ticker=ticker,
            x_username=x_username,
            thread_id=None,
            turns=turns,
            latest_tweet=latest_tweet,
        )
        return ResearchSessionResult(
            topic=topic,
            session_dir=paths.session_dir,
            thread_id=None,
            latest_tweet=latest_tweet,
            turns=turns,
        )

    session_context = [
        f"Topic: {topic}",
        f"Ticker: {ticker or 'n/a'}",
        f"Research session directory: {paths.session_dir}",
        f"Loose notes directory: {paths.loose_notes_dir}",
        f"Statements directory: {paths.statements_dir}",
        f"Filings directory: {paths.filings_dir}",
        f"Articles directory: {paths.articles_dir}",
        f"Analysis directory: {paths.analysis_dir}",
        f"Conclusions directory: {paths.conclusions_dir}",
        f"Final report path: {paths.final_report_path}",
        f"Tracked agent notes directory: {repo_root / 'agent_notes'}",
    ]

    if latest_tweet and latest_tweet.found:
        session_context.extend(
            [
                f"Latest relevant X/Twitter post source: {latest_tweet.source_url}",
                f"Latest relevant X/Twitter post timestamp: {latest_tweet.posted_at}",
            ]
        )

    prompts = [
        "\n".join(
            [
                "Start a deep stock research session for the topic below.",
                "Use web research as needed.",
                "Collect raw source material first.",
                "Write concise raw notes into loose_notes/.",
                "Save source captures or downloaded source files into documents/statements/, documents/filings/, and documents/articles/ as appropriate.",
                "Do not write the final report yet.",
                "",
                *session_context,
            ]
        ),
        "\n".join(
            [
                "Continue the same research session.",
                "Now synthesize the gathered material into analysis markdown files.",
                "At minimum, cover business quality, product/technology, demand drivers, financials, valuation or multiple framing, risks, catalysts, and market-structure/liquidity.",
                "Write the outputs into analysis/.",
                "Keep the files concise and decision-oriented.",
                "",
                *session_context,
            ]
        ),
        "\n".join(
            [
                "Finish the same research session.",
                "Write concise decision memos into conclusions/ and then write final_report.md.",
                "The final report should summarize the key evidence, open risks, and an actionable view.",
                "Reference the files already created in this session instead of repeating everything.",
                "",
                *session_context,
            ]
        ),
    ]

    thread_id: str | None = None
    for index, prompt in enumerate(prompts):
        turn = _run_codex_turn(
            prompt=prompt,
            repo_root=repo_root,
            profile=profile,
            resume_thread_id=thread_id if index > 0 else None,
            full_auto=full_auto,
            dangerously_bypass=dangerously_bypass,
        )
        thread_id = turn.thread_id
        turns.append(turn)
        _write_manifest(
            paths,
            topic=topic,
            ticker=ticker,
            x_username=x_username,
            thread_id=thread_id,
            turns=turns,
            latest_tweet=latest_tweet,
        )

    return ResearchSessionResult(
        topic=topic,
        session_dir=paths.session_dir,
        thread_id=thread_id,
        latest_tweet=latest_tweet,
        turns=turns,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a structured FinAgent research session and optionally run Codex research turns."
    )
    parser.add_argument("topic", help="Research topic, usually a company or ticker.")
    parser.add_argument("--ticker", help="Ticker symbol to include in the session metadata.")
    parser.add_argument("--x-user", help="Optional X/Twitter username to inspect before research.")
    parser.add_argument(
        "--profile",
        help="Optional Codex profile name. When provided, the tool uses `codex exec -p <profile>`.",
    )
    parser.add_argument(
        "--dangerously-bypass-approvals-and-sandbox",
        action="store_true",
        help="Pass the equivalent Codex flag through for fully automatic research turns.",
    )
    parser.add_argument(
        "--no-full-auto",
        action="store_true",
        help="Do not pass `--full-auto` to Codex.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Create the session folders and manifest without invoking Codex.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    result = do_research(
        topic=args.topic,
        ticker=args.ticker,
        x_username=args.x_user,
        profile=args.profile,
        full_auto=not args.no_full_auto,
        dangerously_bypass=args.dangerously_bypass_approvals_and_sandbox,
        dry_run=args.dry_run,
    )

    print(f"session_dir={result.session_dir}")
    print(f"thread_id={result.thread_id or 'n/a'}")
    if result.latest_tweet:
        print(f"latest_tweet_found={result.latest_tweet.found}")
        print(f"latest_tweet_thread_id={result.latest_tweet.thread_id or 'n/a'}")


if __name__ == "__main__":
    main()
