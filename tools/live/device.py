"""The emulator through MaaFramework's adb controller: screenshots, taps, keys, starting or restarting an app, freezing the bot.

    uv run --group probe python tools/live/device.py [--port 16384] <command> ...

  shot OUT.png                          one screenshot, 1280x720
  tap X Y [--wait S] [--shot OUT.png]   a tap in game pixels (1280x720), then a screenshot after S seconds
  press X Y [--hold S] [--wait S] [--shot OUT.png]   a long press: the finger held still for --hold s (default 1)
  key CODE [--wait S] [--shot OUT.png]  an Android key code: 4 back, 3 home
  start [PACKAGE] [--shots DIR --every S --count N]   start an app (default the game), screenshots while it boots
  restart [PACKAGE] [--wait S] [--shot OUT.png]   stop the app (default the game) and start it again, as the
                                        pipeline's L3 does; with --shot, a screenshot S seconds (30) after the start
  freeze --log run.log --fire RE --pid PID [--arm RE] [--cmd FILE] [--out DIR] [--max S]
                                        commands in the file: shot NAME, tap X Y, press X Y [S], key CODE, start PKG,
                                        plan [S] (shots until a planning phase or an E.G.O card, at most S s), resume

`--port` picks the MuMu instance: 16384 is instance 0, 16416 instance 1. A live test owns the emulator
first (the maalc-live-test skill); these commands act on the user's game account.

**freeze** waits for a line of the bot's run.log matching `--fire` (after one matching `--arm`, when given),
suspends every process under `--pid` (the `bot.py run` pid the detach printed), then runs the commands written
to `--cmd` (default `cmd.txt` beside the log), one a line: `shot NAME`, `tap X Y`, `press X Y [S]`, `key CODE`,
`start PACKAGE`, `plan [S]`, `resume`. The bot resumes on `resume` or after `--max` seconds (150): MaaFramework's waits
run on, so a long freeze can time a node out. Screenshots go to `--out` (default the log's folder) as `HHMMSS.fff-NAME.png`.

`plan [S]` lets the game play on, a shot every 3 s (`HHMMSS.fff-plan-NN.png`), until one shows a planning phase (the Win
Rate label up, BattleTurn) or an E.G.O card (EgoCard), read with tools/live/ego_card.py. It prints `PLANNING <file>` or
`CARD <file>`, and the commands after it in the file run then. It ends at the first of: that screen, S seconds (default
120, printed `PLAN timeout after S s`), or the freeze's own `--max` (printed `PLAN cut by the freeze's --max`, and the
bot resumes at that moment). So S above what is left of `--max` is cut to it: raise `--max` for a longer wait. A
`resume` written while `plan` runs waits until it ends.
"""
from __future__ import annotations

import argparse
import datetime
import re
import sys
import time
from pathlib import Path

from PIL import Image

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:  # run as a script, `live` is not importable until tools/ is on the path
    sys.path.insert(0, str(TOOLS))

GAME = "com.ProjectMoon.LimbusCompany"


def pick(devices, port: int):
    found = [d for d in devices if d.address.endswith(f":{port}")]
    if not found:
        sys.exit(f"no adb device on port {port}: {[d.address for d in devices]}")
    return found[0]


def connect(port: int):
    from maa.controller import AdbController
    from maa.toolkit import Toolkit

    d = pick(Toolkit.find_adb_devices(), port)
    ctl = AdbController(d.adb_path, d.address, d.screencap_methods, d.input_methods, d.config)
    ctl.post_connection().wait()
    return ctl


def shot(ctl, out):
    """Save a screenshot; returns it as MaaFramework hands it out (BGR)."""
    img = ctl.post_screencap().wait().get()
    Image.fromarray(img[..., ::-1]).save(out)
    print("saved", out, flush=True)
    return img


PLAN_LIMIT = 120.0  # s `plan` waits when no time is given
PLAN_EVERY = 3.0  # s between two of its shots


def plan(ctl, out: Path, limit: float, deadline: float) -> None:
    """Shots every PLAN_EVERY s until a planning phase or an E.G.O card shows, `limit` s pass, or `deadline` (the
    freeze's own end) comes: the first of the three ends it, and the line it prints says which."""
    from live import ego_card

    end = time.time() + limit
    cut = deadline < end
    end = min(end, deadline)
    i = 0
    while time.time() < end:
        path = out / f"{stamp()}-plan-{i:02}.png"
        img = shot(ctl, path)
        i += 1
        x, card = ego_card.win_rate_x(img), ego_card.card_up(img)
        print(stamp(), "win rate x", x, "card", card, flush=True)
        if x is not None or card:
            print("PLANNING" if x is not None else "CARD", path, flush=True)
            return
        time.sleep(PLAN_EVERY)
    if cut:
        print(f"PLAN cut by the freeze's --max after {i} shots; the bot resumes now", flush=True)
    else:
        print(f"PLAN timeout after {limit:g} s ({i} shots)", flush=True)


PRESS_HOLD = 1.0  # s a press holds when no time is given


def press(ctl, x: int, y: int, hold: float) -> None:
    """A long press: a swipe that stays on (x, y) for hold seconds."""
    ctl.post_swipe(x, y, x, y, round(hold * 1000)).wait()


def stamp() -> str:
    return f"{datetime.datetime.now():%H%M%S.%f}"[:-3]


def tail(path):
    """New lines of a growing file, from its end on."""
    with open(path, encoding="utf-8", errors="replace") as f:
        f.seek(0, 2)
        while True:
            if line := f.readline():
                yield line
            else:
                time.sleep(0.02)


def wait_fire(lines, fire: re.Pattern, arm: re.Pattern | None = None) -> str | None:
    armed = arm is None
    for line in lines:
        if not armed:
            armed = bool(arm.search(line))
        elif fire.search(line):
            return line


def bot_tree(pid: int):
    import psutil

    return psutil.Process(pid).children(recursive=True)


def run_commands(ctl, cmd: Path, out: Path, deadline: float, poll: float = 0.2) -> None:
    """Run the lines written to cmd until `resume` or the deadline; each read empties the file."""
    while time.time() < deadline:
        lines = cmd.read_text().splitlines() if cmd.exists() else []
        if lines:
            cmd.write_text("")
        for line in lines:
            a = line.split()
            if not a:
                continue
            if a[0] == "resume":
                return
            if a[0] == "tap":
                ctl.post_click(int(a[1]), int(a[2])).wait()
            elif a[0] == "press":
                press(ctl, int(a[1]), int(a[2]), float(a[3]) if len(a) > 3 else PRESS_HOLD)
            elif a[0] == "key":
                ctl.post_click_key(int(a[1])).wait()
            elif a[0] == "start":
                ctl.post_start_app(a[1]).wait()
            elif a[0] == "shot":
                shot(ctl, out / f"{stamp()}-{a[1]}.png")
                continue
            elif a[0] == "plan":
                plan(ctl, out, float(a[1]) if len(a) > 1 else PLAN_LIMIT, deadline)
                continue
            else:
                print("unknown command", line, flush=True)
                continue
            print(stamp(), *a, flush=True)
        time.sleep(poll)


def freeze(a, ctl) -> None:
    line = wait_fire(tail(a.log), re.compile(a.fire), a.arm and re.compile(a.arm))
    print("fire", stamp(), line.strip()[:150], flush=True)
    cmd = Path(a.cmd or Path(a.log).with_name("cmd.txt"))
    cmd.write_text("")  # a command left from an earlier freeze would run at once
    procs = []
    try:
        for p in bot_tree(a.pid):
            if each(p.suspend):
                procs.append(p)
        print("frozen", stamp(), [p.pid for p in procs], flush=True)
        run_commands(ctl, cmd, Path(a.out or Path(a.log).parent), time.time() + a.max)
    finally:
        for p in procs:
            each(p.resume)
        print("resumed", stamp(), flush=True)


def each(call) -> bool:
    """call() for one process of the tree: one that ended meanwhile is skipped, and the rest are not left frozen."""
    try:
        call()
        return True
    except Exception as e:  # psutil.NoSuchProcess, AccessDenied
        print("skipped", e, flush=True)
        return False


RESTART_PAUSE = 3.0  # s between the stop and the start: RecoverL3's post_delay (recovery.json)


def restart(ctl, package: str) -> None:
    """Stop the app, then start it: the pipeline's L3 (RecoverL3, RecoverStartApp)."""
    ctl.post_stop_app(package).wait()
    print(stamp(), "stopped", package, flush=True)
    time.sleep(RESTART_PAUSE)
    ctl.post_start_app(package).wait()
    print(stamp(), "started", package, flush=True)


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=16384)
    sub = ap.add_subparsers(dest="command", required=True)
    sub.add_parser("shot").add_argument("out")
    for name, args in (("tap", ("x", "y")), ("press", ("x", "y")), ("key", ("code",))):
        p = sub.add_parser(name)
        for arg in args:
            p.add_argument(arg, type=int)
        p.add_argument("--wait", type=float, default=1.0)
        p.add_argument("--shot")
        if name == "press":
            p.add_argument("--hold", type=float, default=PRESS_HOLD)
    p = sub.add_parser("start")
    p.add_argument("package", nargs="?", default=GAME)
    p.add_argument("--shots")
    p.add_argument("--every", type=float, default=15)
    p.add_argument("--count", type=int, default=10)
    p = sub.add_parser("restart")
    p.add_argument("package", nargs="?", default=GAME)
    p.add_argument("--wait", type=float, default=30)
    p.add_argument("--shot")
    p = sub.add_parser("freeze")
    p.add_argument("--log", required=True)
    p.add_argument("--fire", required=True)
    p.add_argument("--arm")
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--cmd")
    p.add_argument("--out")
    p.add_argument("--max", type=float, default=150)
    a = ap.parse_args(argv)
    command, ctl = a.command, connect(a.port)
    if command == "shot":
        shot(ctl, a.out)
    elif command in ("tap", "press", "key"):
        if command == "tap":
            ctl.post_click(a.x, a.y).wait()
        elif command == "press":
            press(ctl, a.x, a.y, a.hold)
        else:
            ctl.post_click_key(a.code).wait()
        if a.shot:
            time.sleep(a.wait)
            shot(ctl, a.shot)
    elif command == "start":
        ctl.post_start_app(a.package).wait()
        for i in range(a.count if a.shots else 0):
            time.sleep(a.every)
            shot(ctl, Path(a.shots) / f"boot-{i:02}.png")
    elif command == "restart":
        restart(ctl, a.package)
        if a.shot:
            time.sleep(a.wait)
            shot(ctl, a.shot)
    elif command == "freeze":
        freeze(a, ctl)


if __name__ == "__main__":
    main()
