# RiskFirst — Registration Guide (do this BEFORE Aug 28 15:00 UTC)

**This is the first hard gate.** Registration closes **AT kickoff, Aug 28 15:00 UTC** (verified live page 2026-08-26). No registration = no submission, regardless of code quality. It must be done from a normal browser — lablab.ai is Cloudflare-blocked from fleet egress (verified .67 + .74), a human session passes.

## 3 steps, ~10 minutes

### 1. Enroll on lablab.ai (by Aug 28 15:00 UTC)
- Open lablab.ai → find **"Alpaca AI Trading Agents" Hackathon** (main track: **Options Alpha Agents**).
- Log in / sign up (Google or GitHub), click **Register/Enroll** on the event page.
- That's it for step 1. Nothing else needs to be done before kickoff.

### 2. Create the fresh Alpaca paper account (this week)
- Alpaca → sign up for a **NEW paper trading account** (do NOT reuse an existing one — judged on a fresh account).
- Confirm **Options Level 3** is enabled on it (default in paper; needed for covered calls / CSP).
- Note the **account ID** — submission requires it.

### 3. Give me the keys
- Put the two keys in `/home/surge/cryptobot-train/.env` on cudacuda (.67):
  ```
  ALPACA_API_KEY=...
  ALPACA_SECRET_KEY=...
  ```
- The 1-min `alpaca-key-watch` cron fires the moment it appears → verifies REST + MCP → starts the paper loop → track record accrues unattended for the whole Aug 28–Sep 4 window. I'll handle the rest.

## What happens after keys land (automatic, no further action needed)
1. `alpaca-key-watch` (1-min cron) → verifies REST + MCP → starts `start_paper_loop.sh`.
2. `paper-loop-watch` (1-min cron) restarts the loop if it dies during NY RTH.
3. P&L exports nightly to `state/paper/` (dr_backup bundles it).
4. I dry-run the full flow end-to-end and freeze code by Sep 3 night.

## Also parked for you (not urgent)
- **Public repo push** — gh API token on .67 is invalid; SSH auth works as `drone1337llc-lgtm`. Either drop a new token in or pre-create the repo; I'll push.
- **Build-in-public posts** (optional social track) — 5 drafts ready in `posts/`; post links can be pasted at submission if you want them counted.

Everything else in the kit is done and verified (90/90 tests, cover + reel + 10-slide deck, honest OOS gate 5.88 mean Sharpe). Deadline Sep 4 15:00 UTC.
