# TODO

- Harden `custom_scripts/research_session.py` against long-running Codex sessions and partial failures.
- Replace the Codex-based latest-tweet lookup with a dedicated provider once an approved X/Twitter data path exists.
- Add a downloader pass that saves filings, statements, and articles with normalized filenames and source metadata.
- Add a stock-side accumulation/execution skill for ladder design, pending-notional audits, and session-aware routing.
- Add tests for research-session path creation, Codex event parsing, and session manifest updates.
- Decide whether `research_sessions/` should stay local-only forever or get a tracked template/example subfolder.
