# Iran Brief

**A bilingual news and market digest, delivered through a scheduled Python pipeline.**

Iran Brief collects Iran-related headlines, selects items using explicit rules, translates them into Chinese, appends market snapshots, and formats an email with source links. It was built for a personal information-following workflow: receive a compact English–Chinese digest without manually visiting several feeds.

**Current scope:** personal automation prototype. The repository contains runnable code and a GitHub Actions schedule; repository history alone does not establish uninterrupted operation or delivery success. The current briefing path does not use an LLM or an autonomous agent.

## What it does

- Queries Google News RSS with four search buckets: major-outlet keywords, US institutions, China-related sources, and Iran-related sources.
- Deduplicates identical lowercased headlines and selects up to five items containing numeric details in the headline or feed description.
- Produces paired English/Chinese text using an external translation endpoint, falling back to original text for failed headline translations.
- Adds the latest available S&P 500 daily-close change from Stooq and BTC price/24-hour change from CoinGecko. These are different time windows, not synchronized quotes.
- Includes source URLs and sends HTML email through Resend.
- Supports scheduled or manual execution through GitHub Actions, plus a local macOS variant.
- Provides offline HTML previews with synthetic fixtures; no mail credentials are needed.

Search buckets are query labels, not verified publisher identities or balanced coverage guarantees. Numeric filtering is a selection heuristic, not fact checking.

## Try it without sending email

Requirements: Python 3.9+; `curl` for live data collection. The briefing code uses Python's standard library.

```sh
git clone https://github.com/langtianyuyu/iran-brief.git
cd iran-brief
python3 cloud_iran_brief.py --fixture examples/brief.json --preview preview.html
python3 -m unittest discover -s tests -v
```

Open `preview.html` in a browser. The fixture is explicitly synthetic and is not a sample of real news coverage.

To collect current data but only save a preview:

```sh
python3 cloud_iran_brief.py --preview preview.html
```

This mode contacts news, translation and market endpoints but does not call the email sender.

## Email delivery

Set process environment variables; the Python entry point does not automatically load `.env`:

```sh
export RESEND_API_KEY='your-key'
export MAIL_TO='your-recipient@example.com'
export MAIL_FROM='your-approved-sender@example.com'
export TZ='America/Edmonton'
python3 cloud_iran_brief.py
```

Running without `--preview` attempts to send email. Resend sender/account configuration must permit the selected sender and recipient. Do not commit credentials.

## Architecture

```text
Google News RSS → query buckets → headline deduplication → numeric-detail filter
                                                          ↓
                                                bilingual item formatting
                                                          ↓
Stooq + CoinGecko → market snapshot ───────────────→ escaped HTML + source links
                                                          ↓
                                              preview file OR Resend email
```

`cloud_iran_brief.py` is the primary documented entry point. It escapes external text before HTML rendering, excludes non-HTTP(S) source links, and exits nonzero for uncaught errors. It does not download full article bodies or independently verify claims.

## Scheduled execution

The workflow in `.github/workflows/iran-brief.yml` runs at **14:00 UTC daily**, or via `workflow_dispatch`. Set repository Actions secrets `RESEND_API_KEY`, `MAIL_TO`, and `MAIL_FROM`.

`TZ=America/Edmonton` controls the date label used by the script; it does not change the UTC cron. 14:00 UTC corresponds to 07:00 Edmonton standard time and 08:00 daylight time. Scheduled starts can be delayed; a cron definition is not proof of successful daily delivery.

See [deployment instructions](DEPLOY_GITHUB.md). The local launchd configuration is a legacy alternative containing machine-specific paths; adjust it before use and avoid enabling both schedulers unintentionally.

## Repository map

| File | Responsibility |
|---|---|
| `cloud_iran_brief.py` | Cloud briefing, preview and delivery |
| `daily_iran_brief.py` | Earlier local implementation with somewhat different selection/fallback behavior |
| `.github/workflows/iran-brief.yml` | Scheduled/manual cloud execution |
| `examples/brief.json` | Synthetic offline preview fixture |
| `tests/test_brief.py` | Rendering, deduplication and source-failure checks |
| `run_daily_iran_brief.sh`, `com.codex.iranbrief.plist` | Legacy macOS scheduler setup |
| `questrade_auto_trader.py`, `send_trade_plan_email.py` | Separate experimental trading scripts |

## Reliability boundaries

- Headline/description extraction is not full-article summarization. Multiple reports about the same event may remain after exact-title deduplication.
- Search order can fill all five slots from the first bucket. Diversity and freshness are not independently enforced.
- Feed errors are currently skipped. Empty output does not imply that nothing happened.
- Translation uses an unofficial endpoint without an availability guarantee. A market-line translation error can still fail the run.
- Market snapshots may be stale on non-trading days. Source timestamps are not yet included in the output.
- There is no delivery deduplication, persistent run ledger, structured tracing or measured uptime. Re-running can send duplicate emails.
- Offline tests do not verify live provider availability, translation accuracy or email delivery.

## Separate trading experiment

The Questrade scripts are not connected to news interpretation. They implement a rule-based momentum-plan experiment with explicit confirmation and an enable switch. They are not an LLM trading agent, and no profitability or live-execution claim is made.

The approval document references workflows absent from this checkout. `DAILY_LOSS_LIMIT` is configured but not enforced in the inspected execution path. Execution rebuilds a plan rather than approving an immutable plan artifact; order idempotency and full execution-time validation are not implemented. These files are outside the briefing demo and should not be treated as a validated trading system.

## Planned AI extension — not implemented

1. Add source-grounded LLM summaries with item-level citations and clear uncertainty labels.
2. Evaluate numeric fidelity, unsupported claims, translation accuracy and event deduplication on labeled fixtures.
3. Add Langfuse traces and compare prompt/model variants against the current rule-based baseline.
4. Record source timestamps, partial failures and delivery outcomes in a run ledger.

These are future work, not current capabilities or measured outcomes.

## Project history and ownership

The public Git history begins on **March 4, 2026**. That establishes a repository baseline, not continuous use since that date. The current documentation and preview/test improvements were prepared with AI coding assistance. Portfolio discussion should identify the author's actual decisions, review and validation rather than infer sole authorship of every line.

Suggested GitHub description:

> Bilingual news and market briefing pipeline with RSS collection, source links, scheduled email delivery, and offline HTML previews.

Suggested topics: `python`, `rss`, `news-aggregation`, `automation`, `github-actions`, `email`, `translation`.
