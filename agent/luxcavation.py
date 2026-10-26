"""The Luxcavation daily tasks' decisions, free of MaaFramework (docs/spec/03-decisions.md section 15, #367).

actions.py reads the Enkephalin Modules and the battle's result and taps; everything here is plain data in, a step out.
"""

# What the next step is (decide): SKIP and FINISH end the task a success, STOP a failure.
SKIP, FIGHT, RETRY, FINISH, STOP = "skip", "fight", "retry", "finish", "stop"

EXP_COST = 3  # the Modules one EXP Luxcavation battle takes, the hardest stage's (live 2026-10-26: stages 4-9 take 3)
THREAD_COST = 2  # a Thread Luxcavation battle's, every level of Lust's Level Select (live 2026-10-26: Lv20-60 all take 2)


def needed(cost, count):
    """The Modules `count` battles take: the task's one check at its start."""
    return cost * count


def decide(modules, cost, count, won, retried, retries, result=None):
    """The next step of a Luxcavation task.

    result None: no battle just ended, the task is starting; the Modules `modules` must cover all `count` battles
    (SKIP when they do not) before the first FIGHT. Later a result is "win" or "lose", `won` the battles won before it
    and `retried` the retries used before it: a win counts and goes on (FIGHT) until `count` are won (FINISH); a defeat
    counts for nothing and takes no Module, and plays the same stage again (RETRY) while `retries` lasts, else STOP.
    """
    if result is None:
        return SKIP if modules < needed(cost, count) else FIGHT
    if result == "win":
        return FINISH if won + 1 >= count else FIGHT
    return RETRY if retried < retries else STOP
