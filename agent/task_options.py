"""A task's options (#776, #777): the values its entry action (TaskStart, and LuxStart and ChargeStart built on it) reads
once, before any tap, and keeps in actions.TASK["options"]; every reader takes them from there, none from the settings
file.

They still come from the settings file: its run, luxcavation.<task> and charge_enkephalin sections. The two rules that
cross them with the teams are checked here, at the task's start, not when the file loads (settings.cross_check)."""

# The settings' run keys every task reads: the stop procedure's webhook, the title's two dialogs, the kept screens.
GLOBAL = ("webhook_url", "auto_accept_terms", "auto_download", "keep_dismissed_screens")
# The rest of run: MirrorDungeon's own.
MIRROR = ("difficulty", "target_floor", "runs", "theme_pack_refresh", "weekly_bonus_use", "weekly_bonus_amount",
          "stop_when_weekly_bonus_out", "starlight_unaffordable", "wipe_retries", "after_retries")


def common(settings):
    """The options of a task that has none of its own (AssembleModules, ClaimMail, ClaimPassMissions): GLOBAL."""
    return {key: settings["run"][key] for key in GLOBAL}


def mirror(settings):
    """MirrorDungeon's options: GLOBAL and MIRROR."""
    return {**common(settings), **{key: settings["run"][key] for key in MIRROR}}


def luxcavation(settings, key):
    """A Luxcavation task's options (key "exp" or "thread"): GLOBAL and luxcavation.<key>'s mode, count, team, retries
    and consecutive."""
    return {**common(settings), **settings["luxcavation"][key]}


def charge(settings):
    """ChargeEnkephalin's options: GLOBAL and count, charge_enkephalin.count."""
    return {**common(settings), "count": settings["charge_enkephalin"]["count"]}


def target_floor_errors(options, teams):
    """MirrorDungeon's rule (#385): a target floor past 5 needs the whole run HARD, so the difficulty is not normal and
    every enabled team (the rotation picks from them) plays HARD from floor 1 and is not normal_only. Floors 6+ open only
    when every floor of the run was HARD. The errors in the words and settings paths the file's load gave them."""
    target_floor = options["target_floor"]
    if target_floor <= 5:
        return []
    errors = []
    need = f"but target_floor {target_floor} needs the whole run HARD"
    if options["difficulty"] == "normal":
        errors.append(f"run/difficulty: difficulty is 'normal', {need}")
    for i, t in enumerate(teams):
        if not t["enabled"]:
            continue
        if t["usage"] == "normal_only":
            errors.append(f"teams/{i}/usage: team {t['name']!r} is normal_only, {need}")
        if t["hard_from_floor"] is None:
            errors.append(f"teams/{i}/hard_from_floor: team {t['name']!r} never switches to HARD, {need} (hard_from_floor 1)")
        elif t["hard_from_floor"] != 1:
            errors.append(f"teams/{i}/hard_from_floor: team {t['name']!r} starts HARD at floor {t['hard_from_floor']}, {need} (hard_from_floor 1)")
    return errors


def team_errors(key, team, teams):
    """A Luxcavation task's rule (#366): its team (an id, None when none is picked) is one of teams, enabled or not. The
    error in the words and settings path the file's load gave it."""
    if team is not None and team not in {t["id"] for t in teams}:
        return [f"luxcavation/{key}/team: team {team!r} is not in teams"]
    return []
