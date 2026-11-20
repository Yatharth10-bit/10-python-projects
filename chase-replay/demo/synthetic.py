"""Generate fictional, deterministic Cricsheet-shaped T20 records for an offline demo."""

import random
from datetime import date, timedelta


def innings(team, rng, rates, target=None):
    overs = []
    total = outs = 0
    for number in range(20):
        deliveries = []
        for _ in range(6):
            dismissed = rng.random() < 0.055
            runs = 0 if dismissed else rng.choices([0, 1, 2, 4, 6], weights=rates)[0]
            delivery = {"runs": {"batter": runs, "extras": 0, "total": runs}}
            if dismissed:
                delivery["wickets"] = [{"kind": "bowled"}]
                outs += 1
            total += runs
            deliveries.append(delivery)
            if outs == 10 or (target is not None and total >= target):
                break
        overs.append({"over": number, "deliveries": deliveries})
        if outs == 10 or (target is not None and total >= target):
            break
    record = {"team": team, "overs": overs}
    if target is not None:
        record["target"] = {"runs": target, "overs": 20}
    return record, total


def matches(count=36):
    rng = random.Random(128)
    for n in range(count):
        first, score = innings("Rockets", rng, [32, 37, 12, 14, 5])
        boundary_weight = rng.randint(8, 21)
        second, chased = innings("Comets", rng, [32, 37, 12, boundary_weight, 5], score + 1)
        winner = "Comets" if chased > score else "Rockets"
        outcome = {"result": "tie"} if chased == score else {"winner": winner}
        day = (date(2025, 1, 1) + timedelta(days=n)).isoformat()
        yield f"fixture-{n + 1:02}", {
            "info": {"dates": [day], "match_type": "T20", "overs": 20,
                     "balls_per_over": 6, "outcome": outcome},
            "innings": [first, second],
        }
