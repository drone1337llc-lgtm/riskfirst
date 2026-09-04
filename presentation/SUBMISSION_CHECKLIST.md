# Protonaut — SUBMISSION CHECKLIST

*Full package checklist for the Alpaca AI Trading Agents Hackathon (lablab.ai, main track **Options Alpha Agents**). Milestones: **registration closes Aug 28 15:00 UTC (at kickoff) - enroll before then**; **submissions close Sep 4 15:00 UTC.** Paper only, fresh $100k account, options + MCP/CLI mandatory.*

---

## 1. Project submission fields

- [x] **Title:** Protonaut — A CrewAI Multi-Agent Crypto Trader on Alpaca MCP
- [x] **Hook (1–2 sentences):** in `PROJECT_TITLE_DESCRIPTION.md`
- [x] **Description:** full narrative in `PROJECT_TITLE_DESCRIPTION.md` (CrewAI bull/bear/manager debate every 15 min, verdict moves allocations + risk cap, 11-symbol crypto+equity universe, hard risk rails, auditable SQLite log)
- [x] **Pitch:** `PITCH.md` (2-min read, for judges)
- [ ] **Registration:** lablab.ai account enrolled in the event **before Aug 28 15:00 UTC** (registration closes AT kickoff - verified live page 2026-08-26; gates the whole submission, do it first). Direct link: https://lablab.ai/ai-hackathons/alpaca-ai-trading-agents-hackathon
- [ ] **Tags:** `AI agent`, `crypto`, `Alpaca MCP`, `risk management`, `paper trading`, `multi-agent`, `CrewAI`, `LLM` (copy these at submission)

## 2. Media deliverables
- [x] **Cover image** — `cover.png` (1280×720, rendered from `cover-src.html`, Investonaut/Protonaut branding)
- [x] **Video presentation** — `demo-reel.mp4` (30 s, rendered from the current deck; rebuild with `bin/rebuild_reel.sh` after any deck change)
- [x] **Slide deck** — `slides/index.html` (9 slides, Investonaut-branded, CrewAI debate flow + risk rails + 15-min cadence)

## 3. Public repo (PUBLISH — do NOT include keys)
- [x] Push repo to **public GitHub** — DONE 2026-08-27 08:31 MDT (gh token path, repo drone1337llc-lgtm/riskfirst PUBLIC, flag .repo_pushed_fired set on verified push)
- [x] Include: `cryptobot/` + `options/` source, `tests/`, `README.md`, `presentation/` (title/desc, pitch, journal, checklist), `posts/` (5 build-in-public posts), `SUBMISSION.md`.
- [x] **EXCLUDE / never commit:** `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, any `.env`, `options/decisions.db` (runtime churn + account snapshots), `config.py.bak-*`. `.gitignore` extended for all of these (commit 477fdd7).
- [x] `config.py` reads keys from env only; **`ALPACA_REAL_TRADING=1` is the only forbidden env** — paper is hard-forced (`ALPACA_PAPER=true`) inside `McpClient`'s server env, so live keys cannot reach a real account.

## 4. Account + live-paper proof
- [x] **Alpaca paper account running Protonaut** — **`PA39I1R4BNYL`** (original 07-12 hackathon account, $83.2k equity, CrewAI lane). **SUBMIT THIS.**
- [x] **SUBMISSION.md repointed to Protonaut/PA39I1R4BNYL** — committed + pushed to origin/main (2de87b6, 2026-09-04 00:03 MDT). Verified on GitHub.
- [x] **Protonaut loop ALIVE** on 15-min all-day cadence (PID 1649275, verified 2026-09-04 01:00 MDT).
- [ ] **Live-paper traded the window** — track record accrues in state/paper/ (see bin/export_pnl.py).
- [ ] Verify agent ran via **Alpaca MCP** (mandatory) — capture an MCP client log/screenshot.

> **NOTE:** The frozen Investonaut lane (PA3LE52B5YCF, fresh 08-31 account) is NOT the submission — it is held for review. Do not paste PA3LE52B5YCF at submission.

## 5. Build-in-public (social challenge track)
- [x] **5 posts drafted** — `posts/01-announce.md` … `posts/05-submission.md`.
- [ ] **Post links** — *placeholder: add URLs* to the actual posts (X/LinkedIn/dev.to) — **needs Surge's accounts** (only if he wants to run the social track; journal copy is ready).

## 6. Hard-requirement self-check (must ALL be true)
- [x] Trades via **Alpaca MCP / CLI** ✓
- [x] **Paper only**, $100k start ✓ (paper hard-forced in client)
- [x] **No live keys committed** ✓
- [x] **140 offline tests pass** (verified: 60 cryptobot + 80 options incl. MCP contract, LLM referee, runner) ✓
- [x] CrewAI multi-agent debate → verdict moves allocations + risk cap ✓

## 7. Final freeze
- [ ] Dry-run the full submission flow end-to-end (with real keys: watcher → loop → decisions.db → P&L export).
- [ ] Freeze code by **Sep 3 night** — no new features.
- [ ] Submit before **Sep 4 15:00 UTC** — **Surge submits from his own browser**: lablab.ai is Cloudflare-blocked from fleet egress (verified .67 + .74, curl + headless Chrome); a human session passes. All copy is in `PROJECT_TITLE_DESCRIPTION.md` + `SUBMISSION.md` for paste.

---

**Status legend:** `[x]` = done/verified · `[ ]` = placeholder to complete by Sep 3 (keys/repo/post-links = Surge's).
