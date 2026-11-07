# MUDS AI Pokerbot — GreatUniHack 2026 ♠️

A **Python, standard-library-only No-Limit Texas Hold'em bot** built for the MUDS AI Pokerbot Challenge at GreatUniHack 2026. It combines position-aware preflop play, hand-equity estimation, pot-odds decisions, and lightweight opponent profiling to adapt to common student-bot strategies.

> **Status:** Local test harness available. The bot has **not** been verified against the organiser's actual starter kit/server. Tournament compatibility and results are not guaranteed.

## Repository

```text
.
├── my_bot.py      # Bot implementation and decide(state) entrypoint
├── test_bot.py    # Standalone scenarios, hand ranking checks, and speed test
├── README.md
└── .gitignore
```

## Quick start

**Requirements:** Python 3.10+; no third-party packages.

```bash
python --version
python test_bot.py
```

On some systems, use `python3 test_bot.py` or `py -3 test_bot.py` instead.

The local script checks 20 game situations, validates returned action types and raise bounds, asserts key hand rankings and 169 preflop hand classes, and reports average decision time on its benchmark. Its benchmark does **not** prove the bot meets the tournament timeout on every machine or state.

## Bot interface

The expected entrypoint is:

```python
from my_bot import decide

result = decide(state)
# {'action': 'fold' | 'check' | 'call' | 'raise', 'amount': int}
```

The state is expected to expose fields such as `my_cards`, `board`, `street`, `pot`, `to_call`, `can_check`, `can_raise`, `min_raise`, `max_raise`, `my_stack`, `my_bet`, `my_seat`, `opponents`, `history`, `hand_number`, `hands_in_match`, and `button`. Missing fields are handled defensively where possible.

Cards are two-character codes: `As` (ace of spades), `Td` (ten of diamonds), etc. Community cards are 0, 3, 4, or 5 cards depending on the betting street.

**Important raise semantics:** This implementation assumes a raise `amount` is the **total target wager for the betting round**, and `min_raise` and `max_raise` are legal total-wager limits. **Verify this against the actual starter kit before submission.** Other engines may define an incremental raise instead, which requires modifying the raise-sizing adapter.

## Strategy overview

| Component | Approach |
| --- | --- |
| Hand evaluation | 5–7 card ranking, including wheel straights, flushes, full houses, and kickers |
| Preflop | Four starting-hand tiers, position-aware opens and defenses, larger premium raises |
| Postflop | Lightweight Monte Carlo equity estimates; compares equity with call price |
| Draws & boards | Detects flush/straight draws and evaluates wet, dry, or paired textures |
| Opponents | Uses available history to estimate VPIP, PFR, aggression, and folds to bets |
| Exploitation | More value betting against loose opponents, caution against tight raises, trapping aggressive opponents |
| Match stage | Adjusts play when short-stacked late in the match; avoids marginal high-risk confrontations when leading |
| Reliability | Action bounds checking and exception-safe fallback behavior |

Postflop equity uses capped random samples (typically 200 on flop/turn, 100 on river), with cached results for repeat states. It is an **estimate against sampled random opponent holdings**, not a calibrated opponent-specific range model. Runtime and win rate depend on the host environment.

## Testing before submission

1. Run `python test_bot.py` and ensure every assertion passes.
2. Open the organiser's official `GameState` class and verify field names, types, valid actions, and **raise amount interpretation**.
3. Run a local match using the organiser's **documented** server or runner commands; these are not included in this repository.
4. Play at least 100 hands each against a calling station, a tight bot, and an aggressive bot. Track chip balance, win rate, invalid actions, and timing.
5. Inspect runner logs for `Traceback`, invalid action/amount, timeout, and automatic-fold events.
6. Confirm the organiser's submission filename and whether only `my_bot.py` is permitted. Submit the required file(s) before the deadline.

## Design notes and limitations

- Opponent statistics are stored **in module-level memory**. They persist across `decide()` calls **only while the Python process stays alive**; a runner that reloads the module or starts a new process each action will reset them.
- The model assumes the simulator exposes enough history and seat information to infer tendencies; absent that information it defaults to a general-purpose strategy.
- Local test states are synthetic and do not replace full-game integration tests.
- The local runner may enforce a different timeout, naming convention, or action schema.
- No external services, data files, or packages are used by the decision code.

## Challenge

Built for the **MUDS AI Pokerbot Challenge, GreatUniHack 2026**. This project is intended exclusively for a closed hackathon simulator, not automated real-money poker.
