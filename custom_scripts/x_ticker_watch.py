from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_scripts.research_session import (
    REPO_ROOT,
    XAccount,
    get_x_account,
    get_x_accounts_for_list,
    load_x_accounts,
    run_structured_json_prompt,
)


ANALYSIS_ROOT = REPO_ROOT / "analysis"
DEFAULT_STATE_PATH = REPO_ROOT / "config" / "x_ticker_watch_state.json"
DEFAULT_ACCOUNTS_LIST = "citrini_affiliates"
MAX_TRACKED_URLS_PER_ACCOUNT = 250
CASHTAG_PATTERN = re.compile(r"(?<![A-Z0-9])\$([A-Z][A-Z0-9]{0,5})(?![A-Za-z0-9])")


@dataclass(frozen=True)
class SourcePost:
    account_key: str
    username: str
    display_name: str | None
    source_url: str
    posted_at: str | None
    text: str
    summary: str | None
    tickers: tuple[str, ...]
    caveats: tuple[str, ...]
    query_thread_id: str | None


@dataclass(frozen=True)
class RelatedPost:
    ticker: str
    username: str
    display_name: str | None
    source_url: str
    posted_at: str | None
    text: str
    summary: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _timestamp_slug(now: datetime | None = None) -> str:
    current = now or _utc_now()
    return current.strftime("%H%M%S")


def _analysis_output_base(output_path: str | None = None, now: datetime | None = None) -> Path:
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    current = now or _utc_now()
    analysis_dir = ANALYSIS_ROOT / current.strftime("%Y-%m-%d")
    analysis_dir.mkdir(parents=True, exist_ok=True)
    return analysis_dir / f"x_ticker_watch_{_timestamp_slug(current)}.json"


def load_poll_state(path: str | None = None) -> dict[str, Any]:
    state_path = Path(path) if path else DEFAULT_STATE_PATH
    if not state_path.exists():
        return {"updated_at": None, "accounts": {}}
    with state_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def write_poll_state(state: dict[str, Any], path: str | None = None) -> Path:
    state_path = Path(path) if path else DEFAULT_STATE_PATH
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state_path


def extract_cash_tickers(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    tickers: list[str] = []
    for match in CASHTAG_PATTERN.finditer(text or ""):
        ticker = match.group(1).upper()
        if ticker not in seen:
            seen.add(ticker)
            tickers.append(ticker)
    return tuple(tickers)


def select_accounts(
    *,
    account_keys: list[str] | None = None,
    list_names: list[str] | None = None,
) -> tuple[XAccount, ...]:
    account_keys = account_keys or []
    list_names = list_names or []

    selected: list[XAccount] = []
    seen: set[str] = set()

    if not account_keys and not list_names:
        list_names = [DEFAULT_ACCOUNTS_LIST]

    for list_name in list_names:
        for account in get_x_accounts_for_list(list_name):
            if account.key not in seen:
                seen.add(account.key)
                selected.append(account)

    for identifier in account_keys:
        account = get_x_account(identifier)
        if account is None:
            raise ValueError(f"Unknown X account: {identifier}")
        if account.key not in seen:
            seen.add(account.key)
            selected.append(account)

    if selected:
        return tuple(selected)

    return load_x_accounts()


def filter_new_posts(posts: tuple[SourcePost, ...], state: dict[str, Any]) -> tuple[SourcePost, ...]:
    new_posts: list[SourcePost] = []
    accounts_state = state.get("accounts", {})
    for post in posts:
        seen_urls = set(accounts_state.get(post.account_key, {}).get("seen_source_urls", []))
        if post.source_url not in seen_urls:
            new_posts.append(post)
    return tuple(new_posts)


def dedupe_posts_by_source_url(posts: tuple[SourcePost, ...]) -> tuple[SourcePost, ...]:
    deduped: list[SourcePost] = []
    seen_urls: set[str] = set()
    for post in posts:
        if post.source_url in seen_urls:
            continue
        seen_urls.add(post.source_url)
        deduped.append(post)
    return tuple(deduped)


def update_state_with_posts(
    state: dict[str, Any],
    posts: tuple[SourcePost, ...],
    *,
    max_urls_per_account: int = MAX_TRACKED_URLS_PER_ACCOUNT,
) -> dict[str, Any]:
    accounts_state = dict(state.get("accounts", {}))
    for post in posts:
        account_state = dict(accounts_state.get(post.account_key, {}))
        seen_urls = list(account_state.get("seen_source_urls", []))
        if post.source_url not in seen_urls:
            seen_urls.insert(0, post.source_url)
        account_state["username"] = post.username
        account_state["seen_source_urls"] = seen_urls[:max_urls_per_account]
        accounts_state[post.account_key] = account_state

    return {
        "updated_at": _utc_now().isoformat(timespec="seconds"),
        "accounts": accounts_state,
    }


def _recent_posts_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["username", "posts", "caveats"],
        "properties": {
            "username": {"type": "string"},
            "posts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["source_url", "posted_at", "text", "summary", "display_name", "caveats"],
                    "properties": {
                        "source_url": {"type": "string"},
                        "posted_at": {"type": ["string", "null"]},
                        "text": {"type": "string"},
                        "summary": {"type": ["string", "null"]},
                        "display_name": {"type": ["string", "null"]},
                        "caveats": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "additionalProperties": False,
                },
            },
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    }


def _related_posts_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["ticker", "posts", "caveats"],
        "properties": {
            "ticker": {"type": "string"},
            "posts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["username", "display_name", "source_url", "posted_at", "text", "summary"],
                    "properties": {
                        "username": {"type": "string"},
                        "display_name": {"type": ["string", "null"]},
                        "source_url": {"type": "string"},
                        "posted_at": {"type": ["string", "null"]},
                        "text": {"type": "string"},
                        "summary": {"type": ["string", "null"]},
                    },
                    "additionalProperties": False,
                },
            },
            "caveats": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
        "additionalProperties": False,
    }


def fetch_recent_account_posts(
    account: XAccount,
    *,
    limit: int,
    since_hours: int,
    timeout_seconds: int,
    profile: str | None = None,
    full_auto: bool = True,
    dangerously_bypass: bool = False,
) -> tuple[tuple[SourcePost, ...], tuple[str, ...]]:
    prompt = "\n".join(
        [
            f"Find up to {limit} of the most recent public X/Twitter posts from @{account.username}.",
            "Use web browsing if needed.",
            f"Focus on posts or thread continuations from the last {since_hours} hours when available.",
            "Ignore likes.",
            "Include replies only when they are substantive market commentary.",
            "Return JSON only under the provided schema.",
            "Keep this fast; if you cannot verify recent posts quickly, return an empty list with caveats.",
            "For each post, include the canonical source URL, timestamp when known, full text, and a concise factual summary.",
            "If recency cannot be fully verified, say so in caveats rather than inventing certainty.",
        ]
    )
    payload, thread_id = run_structured_json_prompt(
        prompt=prompt,
        schema=_recent_posts_schema(),
        profile=profile,
        full_auto=full_auto,
        dangerously_bypass=dangerously_bypass,
        timeout_seconds=timeout_seconds,
    )

    posts = tuple(
        SourcePost(
            account_key=account.key,
            username=payload["username"],
            display_name=entry["display_name"],
            source_url=entry["source_url"],
            posted_at=entry["posted_at"],
            text=entry["text"],
            summary=entry["summary"],
            tickers=extract_cash_tickers(entry["text"]),
            caveats=tuple(entry["caveats"]),
            query_thread_id=thread_id,
        )
        for entry in payload["posts"]
    )
    caveats = tuple(payload["caveats"])
    return posts, caveats


def fetch_related_ticker_posts(
    ticker: str,
    *,
    exclude_usernames: tuple[str, ...],
    limit: int,
    since_hours: int,
    timeout_seconds: int,
    profile: str | None = None,
    full_auto: bool = True,
    dangerously_bypass: bool = False,
) -> tuple[tuple[RelatedPost, ...], tuple[str, ...], str]:
    excludes = ", ".join(f"@{username}" for username in exclude_usernames) or "none"
    prompt = "\n".join(
        [
            f"Find up to {limit} recent public X/Twitter posts materially related to ${ticker}.",
            "Use web browsing if needed.",
            f"Prefer posts from the last {since_hours} hours.",
            f"Exclude these usernames: {excludes}.",
            "Return JSON only under the provided schema.",
            "Keep this fast; if you cannot verify recent relevant posts quickly, return an empty list with caveats.",
            "Only include posts with real ticker-specific relevance, not generic cashtag spam or duplicated reposts.",
            "For each post, include source URL, timestamp when known, full text, and a concise factual summary.",
            "If you cannot confidently verify recency or relevance, keep the list short and explain the uncertainty in caveats.",
        ]
    )
    payload, thread_id = run_structured_json_prompt(
        prompt=prompt,
        schema=_related_posts_schema(),
        profile=profile,
        full_auto=full_auto,
        dangerously_bypass=dangerously_bypass,
        timeout_seconds=timeout_seconds,
    )
    posts = tuple(
        RelatedPost(
            ticker=payload["ticker"],
            username=entry["username"],
            display_name=entry["display_name"],
            source_url=entry["source_url"],
            posted_at=entry["posted_at"],
            text=entry["text"],
            summary=entry["summary"],
        )
        for entry in payload["posts"]
    )
    return posts, tuple(payload["caveats"]), thread_id


def _build_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# X Ticker Watch",
        "",
        f"- Generated at: {report['generated_at']}",
        f"- Accounts: {', '.join(report['account_keys']) or 'n/a'}",
        f"- New source posts: {len(report['source_posts'])}",
        f"- Unique tickers: {', '.join(report['tickers'].keys()) or 'none'}",
        "",
        "## Source Posts",
        "",
    ]

    if not report["source_posts"]:
        lines.append("No new source posts were detected.")
    else:
        for post in report["source_posts"]:
            tickers = ", ".join(post["tickers"]) or "none"
            lines.extend(
                [
                    f"### @{post['username']}",
                    "",
                    f"- Account key: {post['account_key']}",
                    f"- Posted at: {post['posted_at'] or 'n/a'}",
                    f"- Source: {post['source_url']}",
                    f"- Tickers: {tickers}",
                    f"- Summary: {post['summary'] or 'n/a'}",
                    "",
                    post["text"],
                    "",
                ]
            )

    lines.extend(["## Related Posts By Ticker", ""])
    if not report["tickers"]:
        lines.append("No cashtags were extracted from new source posts.")
    else:
        for ticker, data in report["tickers"].items():
            lines.extend(
                [
                    f"### ${ticker}",
                    "",
                    f"- Source post count: {data['source_post_count']}",
                    f"- Related post count: {len(data['related_posts'])}",
                ]
            )
            if data["caveats"]:
                lines.append(f"- Caveats: {'; '.join(data['caveats'])}")
            lines.append("")
            if not data["related_posts"]:
                lines.append("No related posts found.")
                lines.append("")
                continue
            for post in data["related_posts"]:
                lines.extend(
                    [
                        f"- @{post['username']} | {post['posted_at'] or 'n/a'} | {post['source_url']}",
                        f"  {post['summary'] or post['text']}",
                    ]
                )
            lines.append("")

    if report["caveats"]:
        lines.extend(["## Caveats", ""])
        lines.extend(f"- {caveat}" for caveat in report["caveats"])

    return "\n".join(lines).strip() + "\n"


def write_report_files(report: dict[str, Any], output_path: str | Path) -> tuple[Path, Path]:
    json_path = Path(output_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    markdown_path = json_path.with_suffix(".md")
    markdown_path.write_text(_build_markdown(report), encoding="utf-8")
    return json_path, markdown_path


def poll_x_accounts(
    *,
    accounts: tuple[XAccount, ...],
    state_path: str | None = None,
    limit_per_account: int = 5,
    related_limit: int = 5,
    source_since_hours: int = 36,
    related_since_hours: int = 24,
    query_timeout_seconds: int = 180,
    profile: str | None = None,
    full_auto: bool = True,
    dangerously_bypass: bool = False,
    update_state: bool = True,
) -> tuple[dict[str, Any], Path | None]:
    state = load_poll_state(state_path)
    caveats: list[str] = []
    fetched_posts: list[SourcePost] = []

    for account in accounts:
        try:
            posts, account_caveats = fetch_recent_account_posts(
                account,
                limit=limit_per_account,
                since_hours=source_since_hours,
                timeout_seconds=query_timeout_seconds,
                profile=profile,
                full_auto=full_auto,
                dangerously_bypass=dangerously_bypass,
            )
            fetched_posts.extend(posts)
            caveats.extend(account_caveats)
        except Exception as exc:
            caveats.append(f"Failed to poll @{account.username}: {exc}")

    deduped_posts = dedupe_posts_by_source_url(tuple(fetched_posts))
    new_posts = filter_new_posts(deduped_posts, state)
    ticker_counts: dict[str, int] = {}
    for post in new_posts:
        for ticker in post.tickers:
            ticker_counts[ticker] = ticker_counts.get(ticker, 0) + 1

    related_by_ticker: dict[str, Any] = {}
    exclude_usernames = tuple(account.username for account in accounts)
    for ticker in sorted(ticker_counts):
        try:
            related_posts, related_caveats, thread_id = fetch_related_ticker_posts(
                ticker,
                exclude_usernames=exclude_usernames,
                limit=related_limit,
                since_hours=related_since_hours,
                timeout_seconds=query_timeout_seconds,
                profile=profile,
                full_auto=full_auto,
                dangerously_bypass=dangerously_bypass,
            )
        except Exception as exc:
            related_by_ticker[ticker] = {
                "source_post_count": ticker_counts[ticker],
                "related_posts": [],
                "caveats": [f"Failed to fetch related posts for ${ticker}: {exc}"],
                "query_thread_id": None,
            }
            continue

        related_by_ticker[ticker] = {
            "source_post_count": ticker_counts[ticker],
            "related_posts": [asdict(post) for post in related_posts],
            "caveats": list(related_caveats),
            "query_thread_id": thread_id,
        }

    next_state = update_state_with_posts(state, new_posts)
    written_state_path = write_poll_state(next_state, state_path) if update_state else None
    report = {
        "generated_at": _utc_now().isoformat(timespec="seconds"),
        "account_keys": [account.key for account in accounts],
        "state_path": str(Path(state_path) if state_path else DEFAULT_STATE_PATH),
        "source_posts": [asdict(post) for post in new_posts],
        "tickers": related_by_ticker,
        "caveats": caveats,
    }
    return report, written_state_path


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Poll tracked X/Twitter accounts, extract cashtags, and fetch related ticker posts."
    )
    parser.add_argument(
        "--list",
        dest="account_lists",
        action="append",
        default=[],
        help="Tracked X account list name. Repeatable. Defaults to `citrini_affiliates` when omitted.",
    )
    parser.add_argument(
        "--account",
        dest="accounts",
        action="append",
        default=[],
        help="Tracked X account key or username. Repeatable.",
    )
    parser.add_argument(
        "--limit-per-account",
        type=int,
        default=5,
        help="Maximum recent posts to inspect per monitored account.",
    )
    parser.add_argument(
        "--related-limit",
        type=int,
        default=5,
        help="Maximum related posts to fetch per extracted ticker.",
    )
    parser.add_argument(
        "--source-since-hours",
        type=int,
        default=36,
        help="Lookback window for monitored account posts.",
    )
    parser.add_argument(
        "--related-since-hours",
        type=int,
        default=24,
        help="Lookback window for related ticker posts.",
    )
    parser.add_argument(
        "--state-path",
        help="Optional path for persistent poll state JSON.",
    )
    parser.add_argument(
        "--query-timeout-seconds",
        type=int,
        default=180,
        help="Maximum seconds to allow each nested Codex X query before failing with a caveat.",
    )
    parser.add_argument(
        "--output",
        help="Optional output JSON path. Defaults to analysis/{today}/x_ticker_watch_<time>.json.",
    )
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
        "--no-state-update",
        action="store_true",
        help="Run the poll without writing back persistent state.",
    )
    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    accounts = select_accounts(
        account_keys=args.accounts,
        list_names=args.account_lists,
    )
    report, state_path = poll_x_accounts(
        accounts=accounts,
        state_path=args.state_path,
        limit_per_account=args.limit_per_account,
        related_limit=args.related_limit,
        source_since_hours=args.source_since_hours,
        related_since_hours=args.related_since_hours,
        query_timeout_seconds=args.query_timeout_seconds,
        profile=args.profile,
        full_auto=not args.no_full_auto,
        dangerously_bypass=args.dangerously_bypass_approvals_and_sandbox,
        update_state=not args.no_state_update,
    )

    output_path = _analysis_output_base(args.output)
    json_path, markdown_path = write_report_files(report, output_path)

    print(f"output_json={json_path}")
    print(f"output_md={markdown_path}")
    print(f"state_path={state_path or 'not_written'}")
    print(f"new_source_posts={len(report['source_posts'])}")
    print(f"unique_tickers={len(report['tickers'])}")


if __name__ == "__main__":
    main()
