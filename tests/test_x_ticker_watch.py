import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from custom_scripts.x_ticker_watch import (
    SourcePost,
    dedupe_posts_by_source_url,
    extract_cash_tickers,
    filter_new_posts,
    select_accounts,
    update_state_with_posts,
    write_report_files,
)


class XTickerWatchTests(unittest.TestCase):
    def test_extract_cash_tickers_preserves_order_and_uniqueness(self) -> None:
        tickers = extract_cash_tickers("Watching $NVDA, $TSM, and $NVDA again with $ARM.")

        self.assertEqual(tickers, ("NVDA", "TSM", "ARM"))

    def test_select_accounts_defaults_to_citrini_list(self) -> None:
        accounts = select_accounts()

        self.assertEqual([account.key for account in accounts], ["citrini", "nick_reece", "zephyr", "jukan"])

    def test_filter_new_posts_uses_seen_source_urls(self) -> None:
        state = {
            "updated_at": None,
            "accounts": {
                "citrini": {
                    "username": "Citrini7",
                    "seen_source_urls": ["https://x.com/Citrini7/status/1"],
                }
            },
        }
        posts = (
            SourcePost(
                account_key="citrini",
                username="Citrini7",
                display_name="Citrini",
                source_url="https://x.com/Citrini7/status/1",
                posted_at="2026-03-12T00:00:00Z",
                text="$NVDA",
                summary="Old post",
                tickers=("NVDA",),
                caveats=(),
                query_thread_id="thread-1",
            ),
            SourcePost(
                account_key="citrini",
                username="Citrini7",
                display_name="Citrini",
                source_url="https://x.com/Citrini7/status/2",
                posted_at="2026-03-12T01:00:00Z",
                text="$TSM",
                summary="New post",
                tickers=("TSM",),
                caveats=(),
                query_thread_id="thread-1",
            ),
        )

        new_posts = filter_new_posts(posts, state)

        self.assertEqual([post.source_url for post in new_posts], ["https://x.com/Citrini7/status/2"])

    def test_dedupe_posts_by_source_url_keeps_first_occurrence(self) -> None:
        posts = (
            SourcePost(
                account_key="citrini",
                username="Citrini7",
                display_name="Citrini",
                source_url="https://x.com/Citrini7/status/2",
                posted_at="2026-03-12T01:00:00Z",
                text="$TSM first",
                summary="First copy",
                tickers=("TSM",),
                caveats=(),
                query_thread_id="thread-1",
            ),
            SourcePost(
                account_key="citrini",
                username="Citrini7",
                display_name="Citrini",
                source_url="https://x.com/Citrini7/status/2",
                posted_at="2026-03-12T01:00:00Z",
                text="$TSM duplicate",
                summary="Second copy",
                tickers=("TSM",),
                caveats=(),
                query_thread_id="thread-1",
            ),
        )

        deduped = dedupe_posts_by_source_url(posts)

        self.assertEqual(len(deduped), 1)
        self.assertEqual(deduped[0].text, "$TSM first")

    def test_update_state_with_posts_tracks_latest_urls(self) -> None:
        state = {"updated_at": None, "accounts": {}}
        posts = (
            SourcePost(
                account_key="nick_reece",
                username="nicholastreece",
                display_name="Nick Reece",
                source_url="https://x.com/nicholastreece/status/10",
                posted_at="2026-03-12T02:00:00Z",
                text="$ARM",
                summary="ARM post",
                tickers=("ARM",),
                caveats=(),
                query_thread_id="thread-2",
            ),
        )

        updated = update_state_with_posts(state, posts, max_urls_per_account=10)

        self.assertEqual(updated["accounts"]["nick_reece"]["username"], "nicholastreece")
        self.assertEqual(
            updated["accounts"]["nick_reece"]["seen_source_urls"],
            ["https://x.com/nicholastreece/status/10"],
        )

    def test_write_report_files_persists_json_and_markdown(self) -> None:
        report = {
            "generated_at": "2026-03-12T03:00:00+00:00",
            "account_keys": ["citrini"],
            "state_path": "config/x_ticker_watch_state.json",
            "source_posts": [
                {
                    "account_key": "citrini",
                    "username": "Citrini7",
                    "display_name": "Citrini",
                    "source_url": "https://x.com/Citrini7/status/3",
                    "posted_at": "2026-03-12T03:00:00Z",
                    "text": "$NVDA still matters",
                    "summary": "NVDA mention",
                    "tickers": ["NVDA"],
                    "caveats": [],
                    "query_thread_id": "thread-3",
                }
            ],
            "tickers": {
                "NVDA": {
                    "source_post_count": 1,
                    "related_posts": [],
                    "caveats": [],
                    "query_thread_id": "thread-4",
                }
            },
            "caveats": [],
        }

        with TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "watch.json"
            json_path, markdown_path = write_report_files(report, output_path)

            self.assertTrue(json_path.exists())
            self.assertTrue(markdown_path.exists())
            self.assertIn("Citrini7", json_path.read_text(encoding="utf-8"))
            self.assertIn("$NVDA", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
