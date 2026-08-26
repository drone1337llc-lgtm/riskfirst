# Post 4 — The Circuit-Breaker (Sep 1)

**When the −10% trip fires, the book goes flat.**

Trading agents fail one of two ways: slowly (fees bleed) or spectacularly (one bad thesis, one uncapped leg). The circuit-breaker kills the spectacular mode.

How it works:
- Every decision cycle, the agent checks equity vs its running high-water mark
- At **−10% trailing drawdown**: all positions flatten, no new entries
- It's a *trailing* breaker — the reference is the equity high-water mark, so a recovery to within 10% of the high re-arms it for the next trip

Why I like it: most agents treat memory as a prompt string. This is memory as a *state machine* — the book remembers it was hurt and refuses to keep trading through the drawdown.

Same pattern is what kept the crypto secondary lane alive: the OOS gate showed fold 2 at −9.43 Sharpe — the same lane that would trip the breaker hard in live trading, which is exactly why it's demoted.

Also: the daily-loss circuit (−3% intraday) and the drawdown pause (−8%, blocks new entries) are the earlier rungs of the same ladder. The −10% breaker is the last-resort flatten.
