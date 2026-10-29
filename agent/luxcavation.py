"""The Luxcavation daily tasks' decisions, free of MaaFramework (docs/spec/03-decisions.md section 15, #367).

actions.py reads the Enkephalin Modules and the battle's result and taps; everything here is plain data in, a step out.
"""

import re

# What the next step is (decide): SKIP and FINISH end the task a success, STOP a failure.
SKIP, FIGHT, RETRY, FINISH, STOP = "skip", "fight", "retry", "finish", "stop"

EXP_COST = 3  # the Modules one EXP Luxcavation battle takes, the hardest stage's (live 2026-10-26: stages 4-9 take 3)
THREAD_COST = 2  # a Thread Luxcavation battle's, every level of Lust's Level Select (live 2026-10-26: Lv20-60 all take 2)


def needed(cost, count):
    """The Modules `count` battles take: the task's one check at its start."""
    return cost * count


MAX_BATCH = 10  # the game's Consecutive Battle goes from 1 to 10


def batch(count, won, consecutive):
    """The wins the next battle takes: the wins left up to the game's 10 as one Consecutive Battle, else one."""
    return min(MAX_BATCH, count - won) if consecutive else 1


def parse_consecutive(read):
    """The N of a read "Consecutive Battle x N" (the sign misreads as x or X), None when no N of 1-10 reads."""
    found = re.search(r"[×xX]\s*(\d+)", read)
    return int(found[1]) if found and 1 <= int(found[1]) <= MAX_BATCH else None


def presses(now, target):
    """The fewest buttons ("one" 1<<, "minus", "plus", "ten" >>10) that take the box from `now` to `target`."""
    if target == now:
        return []
    step = "plus" if target > now else "minus"
    return min([[step] * abs(target - now), ["one"] + ["plus"] * (target - 1), ["ten"] + ["minus"] * (MAX_BATCH - target)], key=len)


def decide(modules, cost, count, won, retried, retries, result=None, size=1):
    """The next step of a Luxcavation task.

    result None: no battle just ended, the task is starting; the Modules `modules` must cover all `count` battles
    (SKIP when they do not) before the first FIGHT. Later a result is "win" or "lose", `won` the battles won before it
    and `retried` the retries this battle used before it (a win resets it, as the mirror's wipe retries): a win counts
    `size` (a Consecutive Battle x N wins N) and goes on (FIGHT) until `count` are won (FINISH); a defeat counts for nothing and takes no Module, and plays the same
    stage again (RETRY) while this battle's `retries` last, else STOP.
    """
    if result is None:
        return SKIP if modules < needed(cost, count) else FIGHT
    if result == "win":
        return FINISH if won + size >= count else FIGHT
    return RETRY if retried < retries else STOP
