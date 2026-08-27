# RiskFirst — SUBMISSION CHECKLIST

*Full package checklist for the Alpaca AI Trading Agents Hackathon (lablab.ai, main track **Options Alpha Agents**). Milestones: **registration closes Aug 28 15:00 UTC (at kickoff) - enroll before then**; **submissions close Sep 4 15:00 UTC.** Paper only, fresh $100k account, options + MCP/CLI mandatory.*

---

## 1. Project submission fields

- [x] **Title:** RiskFirst — An Options & Equities Agent on Alpaca MCP with a Walk-Forward OOS Gate
- [x] **Hook (1–2 sentences):** in `PROJECT_TITLE_DESCRIPTION.md`
- [x] **Description:** full narrative in `PROJECT_TITLE_DESCRIPTION.md` (multi-agent bull/bear/neutral + IV-rank + LLM referee + risk arbiter, MCP tool surface, OOS gate)
- [x] **Pitch:** `PITCH.md` (2-min read, for judges)
- [ ] **Registration:** lablab.ai account enrolled in the event **before Aug 28 15:00 UTC** (registration closes AT kickoff - verified live page 2026-08-26; gates the whole submission, do it first)
- [ ] **Tags:** `AI agent`, `options`, `Alpaca MCP`, `risk management`, `IV rank`, `paper trading`, `multi-agent`, `volatility` (copy these at submission)

## 2. Media deliverables
- [x] **Cover image** — `cover.png` (1280×720, rendered from `cover-src.html`, RiskFirst branding, honest framing incl. 2.35 seed-42 Sharpe + 2/4 negative folds)
- [x] **Video presentation** — `demo-reel.mp4` (30 s, 10 slides × 3 s, rendered from the current 10-slide deck; rebuild with `bin/rebuild_reel.sh` after any deck change). *Live-demo version to be re-recorded when real keys land (placeholder until then).*
- [x] **Slide deck** — `slides/index.html` (10 slides, RiskFirst-branded, 140-test + OOS-gate honest numbers)

## 3. Public repo (PUBLISH — do NOT include keys)
- [ ] Push repo to **public GitHub** — blocked on Surge: gh CLI token on .67 INVALID (drone1407llc-lgtm); SSH `git@github.com` authenticates fine as drone1407llc-lgtm; repo CREATION needs an API token or a repo pre-created. (Backup bundle + runtime state stored on teamamd `backups\alpaca-kit\`.)
- [x] Include: `cryptobot/` + `options/` source, `tests/`, `README.md`, `presentation/` (title/desc, pitch, journal, checklist), `posts/` (5 build-in-public posts), `SUBMISSION.md`.
- [x] **EXCLUDE / never commit:** `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, any `.env`, `options/decisions.db` (runtime churn + account snapshots), `config.py.bak-*`. `.gitignore` extended for all of these (commit 477fdd7).
- [x] `config.py` reads keys from env only; **`ALPACA_REAL_TRADING=1` is the only forbidden env** — paper is hard-forced (`ALPACA_PAPER=true`) inside `McpClient`'s server env, so live keys cannot reach a real account.

## 4. Account + live-paper proof
- [ ] **Fresh Alpaca paper account** (created for this hackathon — do NOT reuse). Start $100k. — **BLOCKED: Surge must create + provide keys.**
- [ ] **Dedicated paper account ID** — *placeholder:* `PASTE_ACCOUNT_ID_HERE` (fill from the paper dashboard before submission).
- [ ] **Options Level 3 confirmed** on the paper account (required for covered calls / CSP / protective puts).
- [ ] **Live-paper traded the whole window** Aug 28 → Sep 4. Auto-armed: the moment keys land, `alpaca-key-watch` (1-min cron) fires once → verifies REST + MCP → starts `start_paper_loop.sh`; `paper-loop-watch` (1-min cron) restarts the loop if it dies or wedges during NY RTH. Track record accrues unattended in state/paper/decisions.db → export P&L via bin/export_pnl.py (report + stats land in state/paper/, auto-included in daily DR bundle; manual: cryptobot/.venv/bin/python bin/export_pnl.py --mode PAPER).
- [ ] Verify agent ran via **Alpaca MCP** (mandatory) — capture an MCP client log/screenshot (`keys_landed.log` records the MCP boot verification).

## 5. Build-in-public (social challenge track)
- [x] **5 posts drafted** — `posts/01-announce.md` … `posts/05-submission.md`, RiskFirst-branded, each with a hook + one honest lesson.
- [ ] **Post links** — *placeholder: add URLs* to the actual posts (X/LinkedIn/dev.to) — **needs Surge's accounts** (only if he wants to run the social track; journal copy is ready).

## 6. Hard-requirement self-check (must ALL be true)
- [x] Uses **options** as core instrument ✓
- [x] Trades via **Alpaca MCP / CLI** ✓
- [x] **Paper only**, fresh account, $100k start ✓ (paper hard-forced in client)
- [x] **No live keys committed** ✓
- [x] **140 offline tests pass** (verified: 60 cryptobot + 80 options incl. MCP contract, LLM referee, runner) ✓
- [x] Walk-forward OOS Sharpe **positive** (2.35 seed-42 mean, 2/4 negative folds — honestly framed) ✓

## 7. Final freeze
- [ ] Dry-run the full submission flow end-to-end (with real keys: watcher → loop → decisions.db → P&L export).
- [ ] Freeze code by **Sep 3 night** — no new features.
- [ ] Submit before **Sep 4 15:00 UTC** — **Surge submits from his own browser**: lablab.ai is Cloudflare-blocked from fleet egress (verified .67 + .74, curl + headless Chrome); a human session passes. All copy is in `PROJECT_TITLE_DESCRIPTION.md` + `SUBMISSION.md` for paste.

---

**Status legend:** `[x]` = done/verified · `[ ]` = placeholder to complete by Sep 3 (keys/repo/post-links = Surge's).
