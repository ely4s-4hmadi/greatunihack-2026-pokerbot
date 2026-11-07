"""GreatUniHack poker bot. Python 3.10+, standard library only.

Assumptions: raise amount is the TOTAL target wager for this betting round;
min_raise/max_raise are legal total targets. Change only raise_to() if the
organiser's engine instead expects incremental raise chips.
"""
import random
from collections import Counter, defaultdict, deque
from itertools import combinations

RANKS = '23456789TJQKA'
SUITS = 'shdc'
DECK = tuple(r + s for r in RANKS for s in SUITS)
RV = {r: i + 2 for i, r in enumerate(RANKS)}
STATS = defaultdict(lambda: {'hands_seen': 0, 'vpip_n': 0, 'pfr_n': 0,
                             'aggr': 0, 'calls': 0, 'faced': 0, 'folded': 0,
                             'vpip': 0.0, 'pfr': 0.0, 'aggression': 0.0,
                             'folds_to_bet': 0.0})
SEEN_EVENTS = set()
SEEN_HANDS = set()
STACK_HISTORY = deque(maxlen=21)
EQUITY_CACHE = {}


def get(o, name, default=None):
    try:
        if isinstance(o, dict):
            v = o.get(name, default)
        else:
            v = getattr(o, name, default)
        return default if v is None else v
    except Exception:
        return default


def integer(v, fallback=0):
    try:
        return max(0, int(v))
    except (ValueError, TypeError, OverflowError):
        return fallback


def safe_action(state):
    call = integer(get(state, 'to_call', 0))
    stack = integer(get(state, 'my_stack', 0))
    if get(state, 'can_check', False) or call == 0:
        return {'action': 'check', 'amount': 0}
    if call <= min(stack, 2) and stack:
        return {'action': 'call', 'amount': 0}
    return {'action': 'fold', 'amount': 0}


def action(name):
    return {'action': name, 'amount': 0}


def cards_ok(cards):
    try:
        xs = list(cards)
        return all(isinstance(c, str) and len(c) == 2 and
                   c[0] in RV and c[1] in SUITS for c in xs) and len(set(xs)) == len(xs)
    except Exception:
        return False


def straight_high(vals):
    s = set(vals)
    if 14 in s:
        s.add(1)
    for h in range(14, 4, -1):
        if all(v in s for v in range(h - 4, h + 1)):
            return h
    return 0


def eval5(cards):
    """Ranking tuple; larger is better. Categories 0..8."""
    v = [RV[c[0]] for c in cards]
    cnt = Counter(v)
    counts = sorted(((n, r) for r, n in cnt.items()), reverse=True)
    flush = len({c[1] for c in cards}) == 1
    sh = straight_high(v)
    if flush and sh:
        return (8, sh)
    if counts[0][0] == 4:
        q = counts[0][1]
        return (7, q, max(x for x in v if x != q))
    if counts[0][0] == 3 and counts[1][0] == 2:
        return (6, counts[0][1], counts[1][1])
    if flush:
        return (5, *sorted(v, reverse=True))
    if sh:
        return (4, sh)
    if counts[0][0] == 3:
        q = counts[0][1]
        return (3, q, *sorted((x for x in v if x != q), reverse=True))
    pairs = sorted((r for r, n in cnt.items() if n == 2), reverse=True)
    if len(pairs) == 2:
        return (2, pairs[0], pairs[1], max(x for x in v if x not in pairs))
    if len(pairs) == 1:
        p = pairs[0]
        return (1, p, *sorted((x for x in v if x != p), reverse=True))
    return (0, *sorted(v, reverse=True))


def evaluate(cards):
    """Direct best-of-5/6/7 evaluator; no 21-combination enumeration."""
    if not 5 <= len(cards) <= 7 or not cards_ok(cards):
        return (-1,)
    vals = [RV[c[0]] for c in cards]
    cnt = Counter(vals)
    suit_groups = defaultdict(list)
    for c in cards:
        suit_groups[c[1]].append(RV[c[0]])
    for sv in suit_groups.values():
        if len(sv) >= 5:
            sf = straight_high(sv)
            if sf:
                return (8, sf)
    quads = sorted((r for r, n in cnt.items() if n == 4), reverse=True)
    if quads:
        q = quads[0]
        return (7, q, max(v for v in vals if v != q))
    trips = sorted((r for r, n in cnt.items() if n >= 3), reverse=True)
    if trips:
        t = trips[0]
        other_pair = sorted((r for r, n in cnt.items() if r != t and n >= 2), reverse=True)
        if other_pair:
            return (6, t, other_pair[0])
    for sv in suit_groups.values():
        if len(sv) >= 5:
            return (5, *sorted(sv, reverse=True)[:5])
    st = straight_high(vals)
    if st:
        return (4, st)
    if trips:
        t = trips[0]
        kickers = sorted((r for r in vals if r != t), reverse=True)[:2]
        return (3, t, *kickers)
    pairs = sorted((r for r, n in cnt.items() if n >= 2), reverse=True)
    if len(pairs) >= 2:
        a, b = pairs[:2]
        return (2, a, b, max(r for r in vals if r != a and r != b))
    if pairs:
        p = pairs[0]
        return (1, p, *sorted((r for r in vals if r != p), reverse=True)[:3])
    return (0, *sorted(vals, reverse=True)[:5])

def hand_code(hole):
    a, b = hole
    ra, rb = a[0], b[0]
    if RV[ra] < RV[rb]:
        ra, rb = rb, ra
    return ra + rb + ('' if ra == rb else ('s' if a[1] == b[1] else 'o'))


def tier(hole):
    """Covers all 169 canonical starting hand classes."""
    h = hand_code(hole)
    if h in {'AA', 'KK', 'QQ', 'JJ', 'AKs', 'AKo'}:
        return 1
    if h in {'TT', '99', 'AQs', 'AJs', 'KQs', 'AQo', 'KQo'}:
        return 2
    if h in {'88', '77', '66', '55', '44', '33', '22',
             'ATs', 'A9s', 'A8s', 'A7s', 'A6s', 'A5s', 'A4s', 'A3s', 'A2s',
             'KJs', 'QJs', 'JTs', 'T9s', '98s', 'AJo', 'KJo', 'QJo', 'JTo'}:
        return 3
    x, y = RV[h[0]], RV[h[1]]
    if h.endswith('s') and (x-y <= 2 or x == 13 and y >= 8 or x == 12 and y >= 8):
        return 4
    return 5


def seat_position(state):
    opponents = get(state, 'opponents', []) or []
    seats = sorted(set([integer(get(state, 'my_seat', 0)),
                        integer(get(state, 'button', 0))] +
                       [integer(get(o, 'seat', get(o, 'id', -1)), -1)
                        for o in opponents if get(o, 'seat', get(o, 'id', None)) is not None]))
    if len(seats) < 2:
        return 'middle'
    me, button = integer(get(state, 'my_seat', 0)), integer(get(state, 'button', 0))
    if me == button:
        return 'late'
    if len(seats) >= 4 and me == seats[(seats.index(button)-1) % len(seats)]:
        return 'late'
    # On heads-up hands the non-button player is BB, not UTG.
    dist = (seats.index(me) - seats.index(button)) % len(seats)
    if dist in (1, 2):
        return 'blind'
    return 'early' if dist < max(3, len(seats)//2) else 'middle'


def update_opponents(state):
    """Consume historical actions only once, including on repeated decisions.

    Accepted events: {hand_number, seat/player, street, action}. A hand is
    counted only when its presence in history is observable. No invented VPIP.
    """
    hist = get(state, 'history', []) or []
    my_seat = integer(get(state, 'my_seat', 0))
    hand_no = integer(get(state, 'hand_number', 0))
    if not isinstance(hist, (list, tuple)):
        return
    for i, e in enumerate(hist[-1500:]):
        seat_raw = get(e, 'seat', get(e, 'player', get(e, 'player_id', None)))
        if seat_raw is None:
            continue
        try:
            seat = int(seat_raw)
        except (ValueError, TypeError):
            continue
        if seat == my_seat:
            continue
        hn = integer(get(e, 'hand_number', get(e, 'hand', hand_no)))
        act = str(get(e, 'action', get(e, 'type', ''))).lower()
        street = str(get(e, 'street', 'preflop')).lower()
        if act not in ('fold', 'check', 'call', 'bet', 'raise'):
            continue
        # A signature deduplicates repeated full histories. Identical same-hand
        # actions without timestamps are distinguishable by their list index.
        eid = get(e, 'event_id', get(e, 'id', None))
        key = ('id', str(eid)) if eid is not None else (hn, i, seat, street, act)
        if key in SEEN_EVENTS:
            continue
        SEEN_EVENTS.add(key)
        s = STATS[seat]
        if (seat, hn) not in SEEN_HANDS:
            SEEN_HANDS.add((seat, hn))
            s['hands_seen'] += 1
        if street == 'preflop':
            if act in ('call', 'bet', 'raise') and (seat, hn, 'vpip') not in SEEN_HANDS:
                SEEN_HANDS.add((seat, hn, 'vpip'))
                s['vpip_n'] += 1
            if act in ('raise', 'bet') and (seat, hn, 'pfr') not in SEEN_HANDS:
                SEEN_HANDS.add((seat, hn, 'pfr'))
                s['pfr_n'] += 1
        if act in ('raise', 'bet'):
            s['aggr'] += 1
        if act == 'call':
            s['calls'] += 1
        if act == 'fold':
            # Only count actual folds to a bet when an explicit indicator exists.
            if get(e, 'facing_bet', False) or integer(get(e, 'to_call', 0)) > 0:
                s['faced'] += 1
                s['folded'] += 1
        elif integer(get(e, 'to_call', 0)) > 0:
            s['faced'] += 1
        s['vpip'] = s['vpip_n']/max(1, s['hands_seen'])
        s['pfr'] = s['pfr_n']/max(1, s['hands_seen'])
        s['aggression'] = s['aggr']/max(1, s['calls'])
        s['folds_to_bet'] = s['folded']/max(1, s['faced'])
    if len(SEEN_EVENTS) > 12000:
        SEEN_EVENTS.clear()  # Bound memory for long sessions.


def opponent_type(state):
    seats = []
    for o in (get(state, 'opponents', []) or []):
        seat = get(o, 'seat', get(o, 'id', None))
        if seat is not None:
            try:
                seats.append(int(seat))
            except (ValueError, TypeError):
                pass
    known = [STATS[x] for x in seats if x in STATS and STATS[x]['hands_seen'] >= 8]
    if not known:
        # Weak fallback when event history is unavailable: infer only extreme
        # immediate behaviour, not unreliable lifetime frequencies.
        observed = [o for o in (get(state, 'opponents', []) or [])
                    if get(o, 'last_action', get(o, 'action', None)) is not None]
        if observed and all(str(get(o, 'last_action', get(o, 'action', ''))).lower()
                            in ('raise', 'bet') for o in observed):
            return 'maniac'
        return 'unknown'
    # High calling frequency matters more than pure VPIP for bluff decisions.
    if any(s['vpip'] > .45 and s['aggression'] < 1.7 for s in known):
        return 'station'
    if any(s['aggression'] > 2.5 for s in known):
        return 'maniac'
    if all(s['vpip'] < .15 for s in known):
        return 'nit'
    if any(s['faced'] >= 5 and s['folds_to_bet'] > .60 for s in known):
        return 'weak-tight'
    if any(s['vpip'] > .45 for s in known):
        return 'loose'
    return 'unknown'


def texture(board):
    if len(board) < 3:
        return False, False
    counts = Counter(c[1] for c in board)
    paired = len({c[0] for c in board}) < len(board)
    flushy = max(counts.values()) >= 3
    v = {RV[c[0]] for c in board}
    if 14 in v:
        v.add(1)
    straighty = any(sum(x in v for x in range(start, start+5)) >= 3
                    for start in range(1, 11))
    return flushy or straighty, paired


def draw_flags(hole, board):
    if len(board) >= 5:
        return False, False, False
    allc = hole + board
    suit_counts = Counter(c[1] for c in allc)
    fd = any(n >= 4 and any(c[1] == s for c in hole)
             for s, n in suit_counts.items())
    v = {RV[c[0]] for c in allc}
    if 14 in v:
        v.add(1)
    oesd = False
    gut = False
    for start in range(1, 11):
        window = set(range(start, start+5))
        present = len(window & v)
        if present == 4:
            missing = next(iter(window - v))
            if missing in (start, start+4):
                oesd = oesd or (start > 1 and start+4 < 14)
                gut = gut or not oesd
            else:
                gut = True
    return fd, oesd, gut


def equity(hole, board, n=None, opponents=1, seed=0):
    """Win+half tie equity vs random opponents; heads-up default.

    For river, opponent hands are sampled, but the board is exactly known.
    """
    if len(hole) != 2 or len(board) not in (0, 3, 4, 5) or not cards_ok(hole + board):
        return 0.0
    n = min(200 if len(board) <= 4 else 100, max(1, integer(n, 200)))
    opponents = min(3, max(1, integer(opponents, 1)))
    key = (tuple(sorted(hole)), tuple(sorted(board)), n, opponents, seed)
    if key in EQUITY_CACHE:
        return EQUITY_CACHE[key]
    rng = random.Random(seed)
    deck = tuple(c for c in DECK if c not in set(hole + board))
    missing = 5 - len(board)
    needed = missing + 2*opponents
    if needed > len(deck):
        return 0.0
    score = 0.0
    for _ in range(n):
        sampled = rng.sample(deck, needed)
        b = board + sampled[:missing]
        hero = evaluate(hole + b)
        villains = [evaluate(sampled[missing+2*j:missing+2*j+2] + b)
                    for j in range(opponents)]
        best = max([hero] + villains)
        if hero == best:
            score += 1.0/(1+sum(v == hero for v in villains))
    result = score/n
    if len(EQUITY_CACHE) > 1500:
        EQUITY_CACHE.clear()
    EQUITY_CACHE[key] = result
    return result


def can_raise_now(state):
    lo = integer(get(state, 'min_raise', 0))
    hi = integer(get(state, 'max_raise', 0))
    return bool(get(state, 'can_raise', False)) and hi >= lo and hi > 0 and integer(get(state, 'my_stack', 0)) > 0


def raise_to(state, desired):
    """Legal total-target raise (engine must define amounts this way)."""
    if not can_raise_now(state):
        return None
    lo = integer(get(state, 'min_raise', 0))
    hi = integer(get(state, 'max_raise', 0))
    stack = integer(get(state, 'my_stack', 0))
    my_bet = integer(get(state, 'my_bet', 0))
    # A total target cannot normally exceed current contribution + remaining chips.
    hi = min(hi, my_bet + stack)
    if hi < lo:
        return None
    amount = max(lo, min(hi, integer(desired)))
    return {'action': 'raise', 'amount': amount}


def bet(state, fraction, pot=None, multiplier=None):
    p = integer(get(state, 'pot', 0)) if pot is None else pot
    call = integer(get(state, 'to_call', 0))
    mine = integer(get(state, 'my_bet', 0))
    if multiplier is not None and call:
        target = mine + int(call*multiplier + p*.15)
    else:
        target = mine + call + max(1, round(p*fraction))
    if not p:
        target = max(target, integer(get(state, 'min_raise', 0)))
    return raise_to(state, target)


def decide_inner(state):
    hole = list(get(state, 'my_cards', []) or [])
    board = list(get(state, 'board', []) or [])
    if len(hole) != 2 or len(board) not in (0, 3, 4, 5) or not cards_ok(hole + board):
        return safe_action(state)
    pot = integer(get(state, 'pot', 0))
    call = integer(get(state, 'to_call', 0))
    stack = integer(get(state, 'my_stack', 0))
    hand = integer(get(state, 'hand_number', 0))
    total = integer(get(state, 'hands_in_match', 0))
    if stack == 0:
        return action('check') if call == 0 else action('fold')
    update_opponents(state)
    villain = opponent_type(state)
    pos = seat_position(state)
    late = pos == 'late'
    rng = random.Random(21733 + hand*1103515245 + integer(get(state, 'my_seat', 0))*17 + len(board))
    pot_odds = call / max(1, pot + call)
    start_stack = integer(get(state, 'starting_stack', 0))
    # Fallback estimate if starting_stack not available; do not assume it is my_stack.
    if not start_stack:
        start_stack = integer(get(state, 'initial_stack', 0))
    short_late = bool(total and hand > .8*total and start_stack and stack < .3*start_stack)
    leader = bool(start_stack and stack > 2.0*start_stack)
    if not STACK_HISTORY or STACK_HISTORY[-1][0] != hand:
        STACK_HISTORY.append((hand, stack))
    trend = 0
    if len(STACK_HISTORY) >= 15:
        trend = stack - STACK_HISTORY[0][1]
    can_check = bool(get(state, 'can_check', False)) or call == 0
    if not board:
        t = tier(hole)
        code = hand_code(hole)
        if short_late and t <= 2:
            r = raise_to(state, integer(get(state, 'max_raise', 0)))
            return r or (action('check') if can_check else action('call'))
        # Restrict weaker hands when losing; widen slightly when ahead.
        if trend < 0 and t == 4 and not late:
            t = 5
        if trend > 0 and t == 5 and late and code.endswith('s'):
            t = 4
        big_bet = call > max(pot*.35, stack*.12)
        facing_3bet = call > max(60, pot*.48)
        if t == 1:
            if code in ('AA', 'KK', 'QQ', 'AKs', 'AKo') and call > stack*.20:
                return raise_to(state, integer(get(state, 'max_raise', 0))) or action('call')
            r = bet(state, .85 if code in ('AA', 'KK') else .65,
                    multiplier=(3.2 if code in ('AA', 'KK') else 3.0) if call else None)
            return r or (action('check') if can_check else action('call'))
        if t == 2:
            if not call:
                return bet(state, .6) or action('check')
            if not facing_3bet and call < stack*.17 and (late or pot_odds < .3):
                if call < stack*.075 and rng.random() < .45:
                    return bet(state, .6, multiplier=3) or action('call')
                return action('call')
            return action('fold')
        if t == 3:
            if pos == 'early' and not can_check:
                return action('fold')
            if not call and (late or pos == 'middle'):
                return bet(state, .5) or action('check')
            if not call:
                return action('check')
            pair = code[0] == code[1]
            deep = stack >= call*12
            if not facing_3bet and not big_bet and (late or pos == 'blind' or (pair and deep)):
                return action('call')
            return action('fold')
        if t == 4:
            if not call and late:
                return bet(state, .45) or action('check')
            if can_check:
                return action('check')
            if (late or pos == 'blind') and call <= .07*stack and stack >= 15*call:
                return action('call')
            return action('fold')
        if can_check:
            return action('check')
        return action('call') if call < .05*pot and pos == 'blind' else action('fold')

    made = evaluate(hole + board)
    category = made[0]
    fd, oesd, gut = draw_flags(hole, board)
    wet, paired = texture(board)
    drawn = fd or oesd or gut
    # Seed changes with cards, remaining deterministic at a decision point.
    seed = 1729 + hand*101 + sum(RV[c[0]]*'shdc'.index(c[1]) for c in hole+board)
    eq = equity(hole, board, n=200 if len(board) < 5 else 100, seed=seed)
    if len(board) < 5:
        # Monte Carlo already includes draws. Do NOT double-count draw equity.
        eq = max(eq, .18 if fd else (.16 if oesd else (.08 if gut else 0)))
    # Very rough range adjustment: opponents who raise rarely skew stronger.
    if villain == 'nit' and call:
        eq *= .83
    elif villain in ('station', 'loose'):
        eq = min(.99, eq*1.04)
    elif villain == 'maniac' and call:
        eq = min(.99, eq*1.08)
    spr = stack/max(1, pot)
    top_pair = category == 1 and any(RV[c[0]] == max(RV[b[0]] for b in board) for c in hole)
    premium_made = category >= 4
    # Never automatically treat board-only two pair as our strong value hand.
    board_only = len(board) == 5 and evaluate(board) == made
    strong = category >= 2 and not board_only
    all_in_bet = call >= stack and stack > 0
    if all_in_bet and eq <= .55 and not premium_made:
        return action('fold')
    if leader and not strong and call > .22*stack:
        return action('fold')
    if short_late and eq > .55:
        return raise_to(state, integer(get(state, 'max_raise', 0))) or (action('check') if can_check else action('call'))
    # River: no draws or semi-bluffs left; avoid paying off massive value bets.
    if len(board) == 5:
        if call and category == 1 and call > pot*.50 and villain != 'maniac':
            return action('fold')
        if call > pot*.50 and eq < .30:
            return action('fold')
        if eq > .65 and not board_only:
            if villain == 'maniac' and call and strong:
                return action('call')
            r = bet(state, .86 if villain in ('station', 'loose') else .66,
                    multiplier=2.5 if call else None)
            if r and (not call or eq > pot_odds + .20):
                return r
        if call:
            return action('call') if eq > pot_odds + .08 and (call <= pot*.55 or villain == 'maniac' or category >= 2) else action('fold')
        return action('check')

    if eq > .75:
        if villain == 'maniac' and call and spr > 2:
            return action('call')
        r = raise_to(state, integer(get(state, 'max_raise', 0))) if spr < 2 else bet(
            state, .88 if villain in ('station', 'loose') else .75,
            multiplier=2.5 if call else None)
        return r or (action('check') if can_check else action('call'))
    if eq > .60:
        if call:
            if villain == 'maniac' or call > pot*.45:
                return action('call') if pot_odds < eq else action('fold')
            if strong and rng.random() < .3:
                return bet(state, .55, multiplier=2.5) or action('call')
            return action('call') if pot_odds < eq else action('fold')
        return bet(state, .70 if wet else .55) or action('check')
    if call:
        if eq > .45 and eq > pot_odds + .05:
            return action('call')
        if eq > .35 and drawn and late and pot_odds < eq*.72:
            return action('call')
        if call < .05*pot and eq > .20:
            return action('call')
        return action('fold')
    # C-bets and exploitative bluffs exclusively in position or vs weak-tight.
    scary = wet or paired
    blocker = any(c[0] in 'AK' for c in hole) or drawn
    checked = any(str(get(e, 'action', '')).lower() == 'check' and
                  str(get(e, 'street', '')).lower() == str(get(state, 'street', ''))
                  for e in (get(state, 'history', []) or [])[-10:])
    if villain not in ('station', 'loose', 'maniac') and late and scary and blocker and checked:
        chance = .30 if villain in ('nit', 'weak-tight') else .14
        if rng.random() < chance and (len(board) != 5 or eq >= .25):
            return bet(state, .70 if villain == 'weak-tight' else .50) or action('check')
    if villain == 'weak-tight' and late and eq > .32 and rng.random() < .55:
        return bet(state, .70) or action('check')
    return action('check')


def decide(state) -> dict:
    """Tournament entrypoint. Always returns a legal-looking action dict."""
    try:
        result = decide_inner(state)
        if not isinstance(result, dict) or result.get('action') not in ('fold', 'check', 'call', 'raise'):
            return safe_action(state)
        if result['action'] == 'raise':
            if not can_raise_now(state):
                return safe_action(state)
            lo, hi = integer(get(state, 'min_raise', 0)), integer(get(state, 'max_raise', 0))
            if not lo <= integer(result.get('amount', -1)) <= hi:
                return safe_action(state)
        result['amount'] = integer(result.get('amount', 0))
        if result['action'] == 'check' and not (bool(get(state, 'can_check', False)) or integer(get(state, 'to_call', 0)) == 0):
            return safe_action(state)
        if result['action'] == 'call' and integer(get(state, 'to_call', 0)) > integer(get(state, 'my_stack', 0)):
            return action('fold')
        return result
    except Exception:
        return safe_action(state)
