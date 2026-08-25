# Post 4 — The Circuit-Breaker (Sep 1)

** When the −10% trip fires the book goes flat.**

Trading agents fail one of two ways: slowly (fees bleed) or spectacularly (one bad thesis, one uncapped leg). The circuit-breaker kills the spectacular mode.

How it works:
- Every decision cycle, the agent checks equity vs its high-water mark
- At **−10% drawdown**: all positions flatten, no new entries
- Recovery isn't automatic — the breaker is a **process**, not a vibe. It requires re-arming after review, which forces a human-grade pause instead of a model just talking itself back into the market

Why I like it: most agents treat memory as a prompt string. This is memory as a *state machine* — the book remembers it was hurt and refuses to pretend otherwise.

Same pattern is what kept the crypto secondary lane alive: the OOS gate showed fold 2 at −9.43 Sharpe — the breaker would have fired there, which is exactly why the lane is demoted.
