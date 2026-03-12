import unittest
from subprocess import TimeoutExpired
from unittest.mock import patch

from custom_scripts.research_session import (
    _run_codex_turn,
    get_x_account,
    get_x_accounts_for_list,
    load_x_account_lists,
    load_x_accounts,
    resolve_x_username,
)


class ResearchSessionXAccountsTests(unittest.TestCase):
    def test_load_x_accounts_includes_citrini_registry(self) -> None:
        accounts = load_x_accounts()
        usernames = {account.username for account in accounts}

        self.assertIn("Citrini7", usernames)
        self.assertIn("nicholastreece", usernames)
        self.assertIn("zephyr_z9", usernames)
        self.assertIn("jukan05", usernames)

    def test_get_x_account_supports_key_and_username(self) -> None:
        by_key = get_x_account("citrini")
        by_username = get_x_account("@Citrini7")

        self.assertIsNotNone(by_key)
        self.assertIsNotNone(by_username)
        self.assertEqual(by_key.username, "Citrini7")
        self.assertEqual(by_username.key, "citrini")

    def test_named_list_resolves_accounts(self) -> None:
        account_lists = load_x_account_lists()
        list_names = {account_list.name for account_list in account_lists}
        accounts = get_x_accounts_for_list("citrini_affiliates")

        self.assertIn("citrini_affiliates", list_names)
        self.assertEqual(
            [account.key for account in accounts],
            ["citrini", "nick_reece", "zephyr", "jukan"],
        )

    def test_resolve_x_username_supports_registry_and_raw_input(self) -> None:
        self.assertEqual(
            resolve_x_username(username=None, account="nick_reece"),
            "nicholastreece",
        )
        self.assertEqual(
            resolve_x_username(username="@jukan05", account=None),
            "jukan05",
        )

    def test_resolve_x_username_rejects_conflicting_inputs(self) -> None:
        with self.assertRaises(ValueError):
            resolve_x_username(username="foo", account="bar")

    @patch("custom_scripts.research_session.subprocess.run")
    def test_run_codex_turn_raises_clear_timeout(self, mock_run) -> None:
        mock_run.side_effect = TimeoutExpired(
            cmd=["codex", "exec"],
            timeout=5,
            stderr="slow query",
        )

        with self.assertRaises(RuntimeError) as ctx:
            _run_codex_turn(prompt="hello", timeout_seconds=5)

        self.assertIn("timed out", str(ctx.exception))
        self.assertIn("timeout_seconds=5", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
