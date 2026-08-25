# VOLTAIR — SUBMISSION CHECKLIST

*Full package checklist for the Alpaca AI Trading Agents Hackathon (lablab.ai). Deadline: **Sep 4, 2026 15:00 UTC.** Paper only, fresh $100k account, options + MCP/CLI mandatory.*

---

## 1. Project submission fields

- [x] **Title:** VOLTAIR — The Autonomous Options Agent
- [x] **Hook (1–2 sentences):** in `PROJECT_TITLE_DESCRIPTION.md`
- [x] **Description:** full narrative in `PROJECT_TITLE_DESCRIPTION.md` (options-core, multi-agent, IV-rank structure selection, risk gates)
- [x] **Pitch:** `PITCH.md` (2-min read, for judges)
- [ ] **Tags:** `AI agent`, `options`, `Alpaca MCP`, `risk management`, `IV rank`, `paper trading`, `multi-agent`, `volatility`

## 2. Media deliverables
- [ ] **Cover image** — *placeholder: create a clean banner* showing the agent architecture (bull/bear/neutral → IV-rank → risk arbiter → Alpaca MCP). 16:9, high contrast, no clutter. Recommended 1280×720.
- [ ] **Video presentation** — *placeholder: record when live track record is ready.* Record ~3 min, desktop capture:
  - [ ] Open intro: what VOLTAIR is + the one-sentence thesis (30s)
  - [ ] Live demo: agent reads chains, debates, risk-gates, submits a paper order, logs to SQLite (90s)
  - [ ] Risk gates walkthrough + the −3%/−8% circuit-breaker behavior (45s)
  - [ ] P&L / OOS Sharpe screen + close (45s)
- [ ] **Slide deck** — *placeholder: build 8–10 slides.* Outline:
  1. Title + hook
  2. The problem (scripts that bleed, options-less, no risk)
  3. The agent architecture (multi-agent diagram)
  4. The IV-rank structure matrix
  5. The risk framework table
  6. How it uses Alpaca MCP + offline testing (77 tests)
  7. The OOS gate + Cryptonaut diagnosis
  8. Live-paper track record
  9. Why it's an agent, not a script
  10. Close / links

## 3. Public repo (PUBLISH — do NOT include keys)
- [ ] Push `alpaca-hackathon/` to a **public GitHub repo** (e.g. `voltair-options-agent`).
- [ ] Include: `options/` source, `tests/`, `README.md`, `PROJECT_TITLE_DESCRIPTION.md`, `PITCH.md`, `BUILD_IN_PUBLIC_JOURNAL.md`.
- [ ] **EXCLUDE / never commit:** `ALPACA_API_KEY`, `ALPACA_SECRET_KEY`, any `.env`, `decisions.db` containing account PII, live account IDs.
- [ ] Add `.gitignore` for `*.env`, `decisions.db`, `__pycache__/`.
- [ ] `config.py` reads keys from env only; **confirm `ALPACA_IS_LIVE` refuse-by-default rail is documented.**

## 4. Account + live-paper proof
- [ ] **Fresh Alpaca paper account** (created for this hackathon — do NOT reuse). Start $100k.
- [ ] **Dedicated paper account ID** — *placeholder:* `PASTE_ACCOUNT_ID_HERE` (fill from the paper dashboard before submission).
- [ ] **Options Level 3 confirmed** on the paper account (required for covered calls / CSP / protective puts).
- [ ] **Live-paper traded the whole window** Aug 28 → Sep 4. Track record in `decisions.db` → export to a `P&L.png`/CSV for the submission.
- [ ] Verify agent ran via **Alpaca MCP** (mandatory) — capture an MCP client log/screenshot.

## 5. Build-in-public (social challenge track)
- [ ] **Post links** — *placeholder: add URLs* to the actual posts (X/LinkedIn/dev.to) reflecting `BUILD_IN_PUBLIC_JOURNAL.md` Day 1–8 entries.
- [ ] At least **3–4 public posts** during the build window, each with a hook + one honest lesson (journal has the copy ready).

## 6. Hard-requirement self-check (must ALL be true)
- [ ] Uses **options** as core instrument ✓
- [ ] Trades via **Alpaca MCP / CLI** ✓
- [ ] **Paper only**, fresh account, $100k start ✓
- [ ] **No live keys committed** ✓
- [x] 36 offline tests pass (verified, incl. MCP contract suite) ✓
- [ ] Walk-forward OOS Sharpe **positive** ✓

## 7. Final freeze
- [ ] Dry-run the full submission flow end-to-end.
- [ ] Freeze code by **Sep 3 night** — no new features.
- [ ] Submit before **Sep 4 15:00 UTC** (buffer, don't cut it close).

---

**Status legend:** `[x]` = done/verified · `[ ]` = placeholder to complete by Sep 3.
