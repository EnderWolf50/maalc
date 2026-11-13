"""Move one page module's code out of agent/actions.py (#676, choice A): the top-level names MODULES gives the module
go to agent/<module>.py unchanged and in their order, and the tests and tools that read one as `actions.<name>` read
`<module>.<name>`.

    uv run python tools/split_actions.py <module>        # lux_actions, or agent/lux_actions.py

It writes:
- agent/<module>.py: the module's docstring, the imports of actions.py its code uses (less the names it does not),
  `from actions import` the names of actions.py it reads, then each moved statement with the comments and blank lines
  above it.
- agent/actions.py: the rest, less the imported names nothing left in it uses.
- agent/main.py: `import <module>` after `import actions`; the import registers the module's custom actions.
- tests/*.py, tools/*.py, tools/live/*.py: `actions.<name>` becomes `<module>.<name>` for a moved name and for an
  import only the module still uses, and `import <module>` follows each statement that binds `actions` there, or
  replaces an `import actions` that nothing reads any more.

It writes nothing and exits 1 when the table does not fit agent/actions.py: a top-level name it does not place or
places twice, a name of the module that actions.py does not hold, moved code that declares a global or reads a name
of another page module, or code staying in actions.py that reads a moved name (both would be an import cycle). It
prints what a person edits by hand: `getattr(actions, "<moved name>")`, an `actions.<moved name>` left in a comment, a
string or docs/, a read whose `actions` it cannot trace to an import, an assignment or a function's parameter, a
test that sets a name the module binds on actions alone (`setattr(actions, "tap", ...)`, `actions.ROOT = ...`: the
module never reads it; agent_patch's patch_all and rebind set both), and the lines of the agent modules the new
module imports whose docstring points at actions.py.

Then `uv run python tools/move_check.py --module <module> origin/main HEAD` lists what is not a move.
"""

import ast
import re
import symtable
import sys
import textwrap
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parent.parent

# #676 "新檔與分工": each page module's docstring and the top-level names it takes from actions.py, in their order there.
# An expression statement that registers a custom name (AgentServer.custom_recognition("X")(...)) goes by that name.
MODULES = {
    "lux_actions": (
        "Luxcavation's custom actions: the start and the drive, the Luxcavation home, the EXP pass, the entry with its "
        "consecutive battles, and the result.",
        ("module_count", "LUX", "LuxStart", "modules_now", "OpenDrive", "LuxHome", "plan", "ExpPassRead", "battle_over",
         "CONSECUTIVE", "ENTER_AT", "consecutive_box", "consecutive_now", "set_consecutive", "LuxEnter", "LUX_CONFIRM",
         "LuxResult")),
    "daily_actions": (
        "The daily tasks' custom actions: Assemble Modules, Charge Enkephalin, the mail and the pass.",
        ("MailDone", "PassClaimable", "PASS_CLAIMS", "PassFinish", "MODULE_COST", "ENK_BAR", "ASSEMBLE_MAX",
         "MODULES_TAB", "PANEL_CONFIRM", "PANEL_CANCEL", "ASSEMBLE_TRIES", "fractions", "read_fractions", "panel_read",
         "cancel_stop", "on_modules_tab", "too_many", "open_enkephalin", "AssembleMain", "AssemblePanel", "LUNACY_TAB",
         "CHARGE_TRIES", "ChargeStart", "ChargeMain", "ChargePanel")),
    "run_start_actions": (
        "A run's start: the plan, Parallel Mode, the team, starlight and its graces, the starting gift and its search, "
        "and the theme pack.",
        ("WEEKLY_SLOTS", "TEAM_LIST", "ENTER_DIALOG", "TEAM_TITLE", "LEVEL_WARNING", "STARLIGHT_HEADER",
         "STARLIGHT_DIALOG", "STARTING_GIFT_HEADER", "STARLIGHT_AVAILABLE", "STARLIGHT_NOTE", "STARLIGHT_OWNED",
         "GRACE_ORIGIN_X", "GRACE_ORIGIN_Y", "PACK_TITLES", "PACK_CARDS", "CARDS_SETTLE", "REFRESH_BUTTON",
         "REFRESH_BRIGHT", "REFRESH_LIT_MIN", "PlanRun", "INFINITY_TITLE", "INFINITY_BUTTON", "ParallelModeOff",
         "team_rows", "team_list_top", "pick_team_slot", "SelectTeam", "LuxSelectTeam", "grace_box", "grace_selected",
         "read_available", "BuyStarlight", "ConfirmStarlight", "PickStartingGift", "GiftGet", "GIFT_WINDOWS",
         "GRID_SWITCH_TIMEOUT", "SEARCH_TABS", "SEARCH_COUNT", "SEARCH_OWNED", "SEARCH_PANEL_Y", "SEARCH_SELECT",
         "SEARCH_REFUSE", "SEARCH_DIALOG", "FORGO_DIALOG", "SEARCH_DIALOG_BUTTONS", "SEARCH_ICON_MIN", "GRID_MID",
         "GiftSearch", "theme_pack_plan", "pack_ids", "note_pack", "pack_titles", "refresh_lit", "PickThemePack")),
    "map_actions": (
        "The mirror's map: entering a node, routing the floor, and forfeiting the run.",
        ("BUS_HOME", "BUS_SLACK", "BUS_REST", "SLOT", "BUS_TAP", "slot_centre", "bus_tap", "LINKS", "BUS_PROBE",
         "BUS_LINK", "MARKS", "SHOP_ICONS", "ENTER", "MAP_RETRIES", "MAP_LOOKS", "MAP_NEAR", "BAR_BOTTOM", "MAP_DRAGS",
         "PANEL_REWARDS", "PANEL_COST", "MAP_TITLE", "MAP_LEAVING", "MAP_PAN_LIMIT", "PAN_LOOK_MIN", "BUS_JITTER",
         "MAP_ANSWER", "MAP_TAP_LIMIT", "node_marks", "shop_icon", "node_at", "coin_cut_by_bar", "difficulty_costs",
         "coin_text", "coin_number", "coin_part", "cost_miss", "map_data", "is_hard", "map_weights", "map_floor",
         "enter_node", "EnterNode", "RouteMap", "GEAR", "FORFEIT", "FORFEIT_CONFIRM", "FORFEIT_DIALOG", "forfeit")),
    "battle_actions": (
        "A battle's custom actions: the formation, the turns, and the battle's end in a victory or a wipe.",
        ("CARD_X", "CARD_ART_Y", "CARD_NUMBER_Y", "CARD_TAP_Y", "PARTICIPANTS", "DETAILS_BUTTON", "CLEAR_SELECTION",
         "RESET_DIALOG", "RESET_CONFIRM", "PICK_RETAP", "PICK_SETTLE", "card_xy", "participants", "dead_sinners",
         "order_marks", "FORMATION_BACK", "Formation", "WIN_RATE", "START_DISC", "TURN_NUMBER", "SLOT_PORTRAIT_Y",
         "LOWER_Y", "GUARD_TAP_WAIT", "lower_x", "guard_score", "lower_skills", "win_rate_on", "start_shown",
         "turn_started", "START_WAIT", "START_LEAST", "PLAQUE_WAIT", "press_start", "HOLD_SPOT", "HOLD_EVERY",
         "HOLD_LIMIT", "BATTLE_POPUPS", "BATTLE_LEFT", "hold_turn", "HoldTurn", "GUARD_DRAGS", "PlayTurn", "Victory",
         "DEFEAT_OPTIONS", "DEFEAT_CONFIRM", "DEFEAT_TEXT", "Wipe")),
    "event_actions": (
        "An encounter's pages: the event and its choices, the reward cards, and the gift choice.",
        ("EVENT_BUTTON", "EVENT_STORY", "CHOICES_HEADER", "CHOICE_ROWS", "CHECK_PROMPT", "EVENT_PORTRAIT_X",
         "EVENT_PORTRAIT_Y", "EVENT_NEUTRAL", "EVENT_CARD", "EVENT_TEXT_TAPS", "EVENT_TAP_EVERY", "EVENT_READ_EVERY",
         "EVENT_TAKE", "EVENT_LABELS", "EVENT_BUTTON_LABEL", "EVENT_MAP_REST", "EVENT_LIMIT", "EVENT_ODDS_WAIT",
         "EVENT_GAP", "EVENT_LEAST", "CHOICE_X", "CHOICE_STEP", "CHOICE_SCROLLS", "event_table", "red_button",
         "card_alone", "Event", "REWARD_TITLE", "REWARD_CARDS", "CARD_TEXT", "SELECTABLE", "CARD_CONFIRM", "CARD_ROUNDS",
         "CARD_REREADS", "RewardCard", "GIFT_CARDS", "GIFT_COUNT", "GIFT_SELECT", "REFUSE_GIFT", "TRIAL_HALF",
         "TRIAL_NAME_FOOT", "TRIAL_BADGE_X", "gift_count", "gift_tier", "trial_card", "gift_cards", "PickGift")),
    "shop_actions": (
        "The mirror's shop: reading its offer and owned gift grids, buying, selling, fusing, healing and replacing a "
        "skill.",
        ("SHOP_COST", "REFRESH", "OFFER_GRID", "DIALOG_TITLE", "PURCHASE_PREVIEW", "PURCHASE", "PURCHASE_CANCEL",
         "KEYWORD_LABELS", "KEYWORD_REFRESH", "KEYWORD_CANCEL", "PAGE_CLOSE", "PAGE_OK", "SHOP_BUTTONS", "FUSE_CENTRE",
         "FUSE_KEYWORD_OK", "FUSE_DIALOG_CONFIRM", "OWNED_GRID", "FUSE_CELLS", "SELL_CELLS", "OFFER_CELLS",
         "OFFER_DRAG_X", "OFFER_DRAG_PX", "OFFER_ABOVE", "OFFER_UNDER", "offer_whole", "FUSE_LIST", "OWNED_LABEL",
         "GRID_DRAG_X", "GRID_STROKE", "GRID_SCROLLS", "GRID_MARGIN", "GRID_SLIP", "GRID_SAME", "CELL_PAGES", "BADGES",
         "BADGE_MIN", "FUSION_IDS", "GIFT_TIERS", "CELL_ICON_ROI", "EX_TIER", "FUSE_CONFIRM", "FUSE_COUNT",
         "FUSE_NEUTRAL", "FORECAST_CHANCE", "FUSE_TRIES", "FUSIONS_PER_PAGE", "TOOLTIP_CLOSE", "SELL_COST", "SELL_GRID",
         "HEAL_TITLE", "HEAL_COST", "HEAL_OPTIONS", "SHOP_PORTRAIT_X", "BOTTOM_RIGHT", "BOTTOM_LABEL", "OUTSIDE",
         "LEAVE_DIALOG", "LEAVE_CONFIRM", "LEAVE_CANCEL", "REPLACE_TITLE", "REPLACE_OWNED", "REPLACE_COST",
         "REPLACE_PREVIEW", "REPLACE_PRICES", "REPLACE_FRAMES", "REPLACE_OPTIONS", "REPLACE_CANCEL", "REPLACE_CONFIRM",
         "REPLACE_ASK", "REPLACE_MARK", "REPLACE_SETTLE", "SELECT_TITLE", "PAY_SWITCH", "cost_in", "read_cost",
         "BAR_GREY", "bar_dead", "note_skills", "cell_state", "note_owned", "owned_change", "buy_list", "cell_role",
         "template_hits", "cell_id", "held", "read_cells", "read_plates", "offer_cell", "cell_line", "gift_shown",
         "close_tooltip", "read_clear", "owned_cells", "owned_top", "owned_label", "grid_top", "whole", "grid_shift",
         "drag_grid", "centre", "matched", "into_view", "cell_at", "fused_cells", "misplaced", "fused_check", "fusions",
         "read_forecast", "tap_keyword", "gift_get", "pick_cells", "recipe_places", "Shop")),
    "settle_actions": (
        "The run's settlement: the result page, the weekly bonuses, and the claim or the give-up.",
        ("RESULT", "WEEKLY_LEFT", "TOGGLE_X", "TOGGLE_ROI", "GIVE_UP", "CLAIM", "REWARD_TITLE_ROI", "FIRST_FLOOR",
         "reward_up", "claim_asks", "toggles", "Settle")),
}
# #676 "留在 actions.py 的": the state, the screen and tap helpers, a run's and a task's way in and out, the hub's
# recognitions, going home and recovery, and the names two or more page modules share. on_map is the shared helper
# the plan's PR 3 makes of Shop.on_map.
STAY = (
    "ROOT", "RUN", "TASK", "STUCK", "SCREENS", "LOG", "end_battle", "TO_BATTLE", "log", "screen", "tap", "back",
    "box_centre", "param", "next_names", "flag_hit", "until", "shows", "gone", "tap_then", "log_change", "tap_moved",
    "tap_settled", "tap_shown", "still", "PageGone", "PageEnded", "on_page", "POPUPS", "COVERS", "TAPPED_THROUGH",
    "ENDS_ON", "page_guard", "hub_name", "hands_back", "grid_moved", "moved", "swipe", "scroll", "SCROLL_HOLD", "drag",
    "press", "ocr", "text", "number", "address", "run_team", "current_run", "stuck", "done", "run_line", "stop",
    "TaskStart", "PASS_NODES", "StuckFlag", "HubText", "GameAway", "LuxCountMode", "StopTask", "go_home",
    "restart_game", "StuckWaiting", "HomeFrozen", "hub_knows", "StaysUnknown", "HomeLost", "DailyRecover", "GoHomeRun",
    "DoneFlag", "node_results", "ocr_texts", "Recover", "nothing_recognised", "keep_unknown", "foreground",
    "forget_game_state", "run_continued", "restart_floor_clock", "settings_now", "allowed", "DISMISSED_AT",
    "DISMISSED_GAP", "GAPPED", "popup_button", "DismissShot", "ConfirmDownload", "UPDATE_RESTARTS", "AcceptUpdate",
    "AGREE_BOXES", "AGREE_SIZE", "AGREE_CONFIRM", "agree_ticked", "AcceptTerms", "Halt", "SETTLE_WITHIN", "TapUntil",
    "finish", "run_packs", "columns", "FEATURE_MATCH", "FEATURE_PAD", "FEATURE_ALIGN", "BACK_KEY", "seen", "saturation",
    "data", "GET_TITLE", "GET_CONFIRM", "GET_NAME", "GIFTS", "GIFT_NAMES", "GIFT_IDS", "owned_now", "leave_shop",
    "want_of", "WHITE_GOSSYPIUM", "avoided_gifts", "DIALOG_TEXT", "DIALOG_CANCEL", "DIALOG_CONFIRM", "on_map")
WIDTH = 120  # a rewritten import line wraps past this
NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef, ast.ListComp, ast.SetComp, ast.DictComp,
          ast.GeneratorExp)


FUNCTIONS = (ast.FunctionDef, ast.AsyncFunctionDef)
DEFS = (*FUNCTIONS, ast.ClassDef)
SCOPES = (*DEFS, ast.Lambda, ast.Module)  # what can bind actions (a comprehension binds only its own targets)
# this tool and the tests of the two: their strings name actions.<name> as examples
OWN = {"tools/split_actions.py", "tools/move_check.py", "tests/test_split_actions.py", "tests/test_move_check.py"}


class Misfit(Exception):
    """The table does not fit agent/actions.py; the message lists each problem."""


class Report(NamedTuple):
    moved: list[str]  # the names moved, in their order
    renamed: dict[str, int]  # repo path -> `actions.<name>` reads pointed at the module
    by_hand: list[str]  # "path:line: why: text" a person edits


def split_lines(text):
    """text's lines with their ends, broken at \\n only, as ast counts them (str.splitlines breaks at \\f too)."""
    return re.findall(r"[^\n]*\n|[^\n]+\Z", text)


def parent_map(tree):
    return {c: p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}


def params(args):
    """The parameters of a function's or lambda's ast.arguments."""
    return [x for x in (*args.posonlyargs, *args.args, *args.kwonlyargs, args.vararg, args.kwarg) if x]


class Source:
    """A Python file's text and its ast, with ast's line and UTF-8 column turned into offsets in the text."""

    def __init__(self, text):
        self.text, self.tree = text, ast.parse(text)
        self.lines = split_lines(text)
        self.eol = "\r\n" if "\r\n" in text else "\n"
        self.starts = [0]
        for line in self.lines:
            self.starts.append(self.starts[-1] + len(line))

    def at(self, lineno, col):
        return self.starts[lineno - 1] + len(self.lines[lineno - 1].encode("utf-8")[:col].decode("utf-8"))

    def span(self, node):
        return self.at(node.lineno, node.col_offset), self.at(node.end_lineno, node.end_col_offset)


def bound(alias):
    """The name an import alias binds."""
    return alias.asname or alias.name.split(".")[0]


def names_of(node):
    """The top-level names a statement defines: a function's or class's, an assignment's targets, or the custom name
    an expression statement registers."""
    if isinstance(node, DEFS):
        return [node.name]
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        return [e.id for t in targets for e in ast.walk(t) if isinstance(e, ast.Name) and isinstance(e.ctx, ast.Store)]
    if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Call) \
            and node.value.func.args and isinstance(node.value.func.args[0], ast.Constant):
        return [node.value.func.args[0].value]
    return []


def own_reads(node):
    """The names node loads in the scope it sits in: not in the body of a function, lambda, class or comprehension it
    holds, whose reads symtable gives (a comprehension's apart from its own targets: Python 3.12 inlines them)."""
    if isinstance(node, ast.Name):
        return {node.id} if isinstance(node.ctx, ast.Load) else set()
    if isinstance(node, FUNCTIONS):
        a = node.args
        parts = [*node.decorator_list, *a.defaults, *a.kw_defaults, node.returns, *(x.annotation for x in params(a))]
    elif isinstance(node, ast.Lambda):
        parts = [*node.args.defaults, *node.args.kw_defaults]
    elif isinstance(node, ast.ClassDef):
        parts = [*node.decorator_list, *node.bases, *(k.value for k in node.keywords)]
    elif isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)):
        targets = {e.id for g in node.generators for e in ast.walk(g.target) if isinstance(e, ast.Name)}
        inner = [*(g.iter for g in node.generators[1:]), *(i for g in node.generators for i in g.ifs),
                 *((node.key, node.value) if isinstance(node, ast.DictComp) else (node.elt,))]
        return own_reads(node.generators[0].iter) | (set().union(*map(own_reads, inner)) - targets)
    else:
        parts = list(ast.iter_child_nodes(node))
    return set().union(*(own_reads(p) for p in parts if p is not None))


def table_reads(table):
    """The module-level names a symtable scope and the scopes in it read."""
    found = {s.get_name() for s in table.get_symbols() if s.is_global() and s.is_referenced()}
    if table.get_type() == "class":  # a class body reads a module name it does not assign as its own local
        found |= {s.get_name() for s in table.get_symbols()
                  if s.is_referenced() and not s.is_assigned() and not s.is_parameter() and not s.is_free()}
    for child in table.get_children():
        found |= table_reads(child)
    return found


class Statement(NamedTuple):
    names: list[str]
    node: ast.stmt
    first: int  # the first line of its text: the line after the statement before it
    reads: set[str]


def statements(src):
    """(the header's last line, [Statement]): the docstring and the imports, then every top-level statement after."""
    body = src.tree.body
    k = 1 if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) else 0
    while k < len(body) and isinstance(body[k], (ast.Import, ast.ImportFrom)):
        k += 1
    if late := [n.lineno for n in body[k:] if isinstance(n, (ast.Import, ast.ImportFrom))]:
        raise Misfit(f"actions.py imports below its header, at line {late}: move them into the header first")
    header_end = body[k - 1].end_lineno if k else 0
    imports = [n for n in body[:k] if isinstance(n, (ast.Import, ast.ImportFrom))]
    held = {i for n in imports for i in range(n.lineno, n.end_lineno + 1)}
    if imports and (odd := [i for i in range(imports[0].lineno, header_end + 1)
                            if i not in held and src.lines[i - 1].strip()]):
        raise Misfit(f"actions.py has a line other than an import among its imports, at line {odd}")
    children = symtable.symtable(src.text, "actions.py", "exec").get_children()
    out, prev = [], header_end
    for node in body[k:]:
        start = min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])
        reads = own_reads(node).union(*(table_reads(c) for c in children if start <= c.get_lineno() <= node.end_lineno))
        out.append(Statement(names_of(node), node, prev + 1, reads))
        prev = node.end_lineno
    return header_end, out


def header_imports(src):
    """[(import node, the names it binds)] of the header, and the group (blank-line separated) of each."""
    groups, last = [], None
    for node in src.tree.body:
        if isinstance(node, ast.Expr) and not groups:
            continue
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            break
        if last is None or node.lineno > last + 1:
            groups.append([])
        groups[-1].append(node)
        last = node.end_lineno
    return groups


def import_text(src, node, keep):
    """node's text with only the names in keep, None for none of them; the original text when it keeps them all."""
    aliases = [a for a in node.names if bound(a) in keep]
    if not aliases:
        return None
    if len(aliases) == len(node.names):
        return "".join(src.lines[node.lineno - 1:node.end_lineno]).rstrip("\r\n")
    names = ", ".join(a.name + (f" as {a.asname}" if a.asname else "") for a in aliases)
    head = "import " if isinstance(node, ast.Import) else f"from {'.' * node.level}{node.module or ''} import "
    return wrapped(head, names, src.eol)


def wrapped(head, names, eol):
    """`head names` on one line, or in parentheses wrapped under the first name past WIDTH."""
    if len(head) + len(names) <= WIDTH:
        return head + names
    lines = textwrap.wrap(names, WIDTH - len(head) - 1, break_on_hyphens=False)
    return head + "(" + (eol + " " * (len(head) + 1)).join(lines) + ")"


def blank_lead(text):
    """How many blank lines text starts with."""
    n = 0
    for line in split_lines(text):
        if line.strip():
            break
        n += 1
    return n


def lead_with(text, blanks, eol):
    """text with exactly `blanks` blank lines before its first line that is not blank."""
    return eol * blanks + text[len("".join(split_lines(text)[:blank_lead(text)])):]


class Plan(NamedTuple):
    header_end: int  # the last line of the docstring and imports
    statements: list[Statement]
    moved: list[Statement]  # the module's, in their order
    out: set[str]  # the names they define
    problems: list[str]  # why the table does not fit; none when it does


def move_plan(src, module, modules=MODULES, stay=STAY):
    """The Plan of moving module's names out of src, actions.py's Source."""
    placed = {}
    problems = []
    for mod, names in [*((m, n) for m, (_, n) in modules.items()), ("actions", stay)]:
        for n in names:
            if n in placed:
                problems.append(f"the table places {n} twice: {placed[n]} and {mod}")
            placed[n] = mod
    header_end, stmts = statements(src)
    defined = {n for s in stmts for n in s.names}
    problems += [f"actions.py:{s.node.lineno}: {n} is not in the table: put it in the module of the code around it"
                 for s in stmts for n in s.names if n not in placed]
    problems += [f"{n} of {module} is not in actions.py" for n in modules[module][1] if n not in defined]
    moved = [s for s in stmts if s.names and all(placed.get(n) == module for n in s.names)]
    problems += [f"actions.py:{s.node.lineno}: {', '.join(s.names)} straddles {module} and another module"
                 for s in stmts if any(placed.get(n) == module for n in s.names) and s not in moved]
    out = {n for s in moved for n in s.names}
    for s in stmts:
        here = s in moved
        for n in sorted(s.reads & defined):
            if here and placed.get(n) not in ("actions", module):
                problems.append(f"actions.py:{s.node.lineno}: {s.names[0]} ({module}) reads {n} of {placed.get(n)}")
            if not here and n in out:
                problems.append(f"actions.py:{s.node.lineno}: {s.names[0] if s.names else 'a statement'} stays in "
                                f"actions.py and reads {n}, which goes to {module}")
        if here and any(isinstance(e, (ast.Global, ast.Nonlocal)) for e in ast.walk(s.node)):
            problems.append(f"actions.py:{s.node.lineno}: {s.names[0]} declares a global, which the move would rebind")
    return Plan(header_end, stmts, moved, out, problems)


def module_text(src, plan, docstring):
    """(the new module's text, the names it takes from actions, the imported names it uses)."""
    eol, reads = src.eol, set().union(*(s.reads for s in plan.moved))
    groups = header_imports(src)
    imported = {bound(a) for g in groups for n in g for a in n.names}
    # constants, then classes, then the rest, as the imports of actions.py order them
    from_actions = sorted((reads & {n for s in plan.statements for n in s.names}) - plan.out,
                          key=lambda n: (0 if n.isupper() else 1 if n[0].isupper() else 2, n))
    blocks = []
    for i, group in enumerate(groups):
        kept = [(n, t) for n in group if (t := import_text(src, n, reads))]
        lines = [t for _, t in kept]
        if i == len(groups) - 1 and from_actions:  # the local group: from actions first of its from-imports
            at = next((j for j, (n, _) in enumerate(kept) if isinstance(n, ast.ImportFrom)), len(kept))
            lines.insert(at, wrapped("from actions import ", ", ".join(from_actions), eol))
        if lines:
            blocks.append(eol.join(lines))
    text = '"""' + eol.join(textwrap.wrap(docstring, WIDTH - 6)) + '"""' + eol * 2 + (eol * 2).join(blocks) + eol
    prev = None
    for s in plan.moved:
        chunk = "".join(src.lines[s.first - 1:s.node.end_lineno])
        index = plan.statements.index(s)
        if prev is None or index != prev + 1:  # a statement not right after the last one moved: its own gap
            chunk = lead_with(chunk, max(blank_lead(chunk), 2 if isinstance(s.node, DEFS) or prev is None else 1), eol)
        text += chunk
        prev = index
    return text.rstrip("\r\n") + eol, set(from_actions), reads & imported


def actions_text(src, plan):
    """(actions.py without the moved statements and the imported names nothing left reads, those names)."""
    eol = src.eol
    kept = [s for s in plan.statements if s not in plan.moved]
    reads = set().union(*(s.reads for s in kept))
    groups = header_imports(src)
    blocks = [eol.join(t for n in g if (t := import_text(src, n, reads))) for g in groups]
    first = groups[0][0].lineno if groups else plan.header_end + 1
    text = "".join(src.lines[:first - 1]) + (eol * 2).join(b for b in blocks if b) + eol
    gap = None  # the leading blank lines of the first statement of a run moved out
    for s in plan.statements:
        chunk = "".join(src.lines[s.first - 1:s.node.end_lineno])
        if s in plan.moved:
            gap = blank_lead(chunk) if gap is None else gap
            continue
        if gap is not None:
            chunk = lead_with(chunk, max(gap, blank_lead(chunk)), eol)
            gap = None
        text += chunk
    tail = "".join(src.lines[plan.statements[-1].node.end_lineno:]) if plan.statements else ""
    dropped = {bound(a) for g in groups for n in g for a in n.names} - reads
    return text + tail, dropped


def main_text(text, module):
    """main.py with `import <module>` among its imports of actions and the page modules, in name order."""
    lines = split_lines(text)
    at = [i for i, line in enumerate(lines) if re.match(r"import (actions|\w+_actions)\b", line)]
    if not at:
        raise Misfit("main.py has no `import actions`")
    eol = "\r\n" if lines[at[0]].endswith("\r\n") else "\n"
    new = f"import {module}  # noqa: E402,F401  registers custom actions{eol}"
    index = next((i for i in at if lines[i].split()[1] > module), at[-1] + 1)
    return "".join(lines[:index]) + new + "".join(lines[index:])


def scope_chain(parents, node):
    """The scopes node sits in that can bind actions, innermost first, the module last."""
    chain = []
    while node in parents:
        node = parents[node]
        if isinstance(node, SCOPES):
            chain.append(node)
    return chain


def own_nodes(scope):
    """The nodes that run in scope itself: not in the body of a function, lambda, class or comprehension in it."""
    stack = [scope.body] if isinstance(scope, ast.Lambda) else list(scope.body)
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, NESTED):
            stack.extend(ast.iter_child_nodes(node))


def bindings(scope, name, parents):
    """The statements of scope that bind name, "param" when one of its parameters does, [] when none does."""
    if isinstance(scope, (*FUNCTIONS, ast.Lambda)) and any(x.arg == name for x in params(scope.args)):
        return "param"
    found = []
    for node in own_nodes(scope):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and any(bound(a) == name for a in node.names):
            found.append(node)
        elif isinstance(node, ast.Name) and node.id == name and isinstance(node.ctx, ast.Store):
            st = node
            while not isinstance(st, ast.stmt):
                st = parents[st]
            found.append(st)
    return found


def binding_scope(parents, node):
    """The scope whose binding of actions a read of it (node) sees: a class body only for a read right in it; None
    when no scope binds it."""
    chain = scope_chain(parents, node)
    return next((s for i, s in enumerate(chain) if not (isinstance(s, ast.ClassDef) and i > 0)
                 and bindings(s, "actions", parents)), None)


def rename(text, module, names):
    """(new text, reads renamed): text's `actions.<name>` for names pointed at module, with `import <module>` after
    each statement that binds actions for them. A read whose actions it cannot trace to an import, an assignment or a
    parameter of a function it leaves as it is."""
    src = Source(text)
    parents = parent_map(src.tree)
    edits, inserts = [], {}  # inserts: offset -> line

    def line_start(st):  # the statement starts its line: an import can go on a line of its own after it
        return not src.lines[st.lineno - 1][:st.col_offset].strip()

    def before(st):  # (offset, line) of `import <module>` on a line of its own before st, at its indentation
        return src.at(st.lineno, 0), f"{src.lines[st.lineno - 1][:st.col_offset]}import {module}{src.eol}"

    def after(st):  # the same on the line after st
        return src.starts[st.end_lineno], f"{src.lines[st.lineno - 1][:st.col_offset]}import {module}{src.eol}"

    for node in ast.walk(src.tree):
        if not (isinstance(node, ast.Attribute) and node.attr in names and isinstance(node.value, ast.Name)
                and node.value.id == "actions"):
            continue
        scope = binding_scope(parents, node)
        found = bindings(scope, "actions", parents) if scope else []
        if not found:
            continue
        if bindings(scope, module, parents):
            pass  # the scope has the module already
        elif found == "param":
            if isinstance(scope, ast.Lambda):
                continue  # no statement to put the import before
            first = next(st for st in scope.body if not (isinstance(st, ast.Expr) and isinstance(st.value, ast.Constant)))
            if not line_start(first):
                continue
            inserts.update([before(first)])
        elif all(isinstance(st, (ast.Import, ast.ImportFrom, ast.Assign, ast.AnnAssign)) and line_start(st) for st in found):
            inserts.update(after(st) for st in found)
        else:
            continue
        edits.append(src.span(node.value) + (module,))
    count = len(edits)
    edits += [(at, at, line) for at, line in inserts.items()]
    new = src.text
    for a, b, rep in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        new = new[:a] + rep + new[b:]
    return (swap_unused(new, module) if count else new), count


def swap_unused(text, module):
    """text with each `import actions` that nothing reads any more, and that `import <module>` follows, turned into
    that import (its comment kept, the line after dropped): an unused import fails ruff F401."""
    src = Source(text)
    parents = parent_map(src.tree)
    read = {binding_scope(parents, n) for n in ast.walk(src.tree)
            if isinstance(n, ast.Name) and n.id == "actions" and isinstance(n.ctx, ast.Load)}
    lines = list(src.lines)
    for scope in [n for n in ast.walk(src.tree) if isinstance(n, (*DEFS, ast.Module))]:
        found = bindings(scope, "actions", parents)
        if scope in read or found == "param":
            continue
        for st in found:
            if isinstance(st, ast.Import) and [(a.name, a.asname) for a in st.names] == [("actions", None)] \
                    and st.end_lineno < len(lines) and lines[st.end_lineno].strip() == f"import {module}":
                lines[st.lineno - 1] = lines[st.lineno - 1].replace("import actions", f"import {module}", 1)
                lines[st.end_lineno] = ""
    return "".join(lines)


def by_hand(path_name, text, names, module, shared=frozenset()):
    """"path:line: why: text" of each line of a file a person still edits after the move: one that names a moved name
    through actions (in code the rename could not trace, a comment, a string or a doc), reads one by a string
    (getattr), imports one from actions, or sets a name of names or shared (those actions and the module both bind) on
    actions alone, which the module never reads (#676 risk 1: patch_all sets both)."""
    pattern = re.compile(r"\bactions\.(?:" + "|".join(map(re.escape, sorted(names))) + r")\b")
    lines = [line.rstrip("\r\n") for line in split_lines(text)]
    found = {i: "still names it" for i, line in enumerate(lines, 1) if pattern.search(line)}
    if path_name.endswith(".py"):
        binds = names | shared

        def on_actions(node):
            return isinstance(node, ast.Name) and node.id == "actions"

        for node in ast.walk(ast.parse(text)):
            if isinstance(node, ast.Call) and len(node.args) > 1 and on_actions(node.args[0]) \
                    and isinstance(node.args[1], ast.Constant) and node.args[1].value in binds:
                call = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
                if call in ("getattr", "hasattr") and node.args[1].value in names:
                    found[node.lineno] = f"{call} by a string"
                elif call in ("setattr", "delattr"):
                    found[node.lineno] = f"sets it on actions alone, not on {module}"
            elif isinstance(node, (ast.Assign, ast.AugAssign, ast.Delete)):
                targets = node.targets if isinstance(node, (ast.Assign, ast.Delete)) else [node.target]
                if any(isinstance(t, ast.Attribute) and on_actions(t.value) and t.attr in shared for t in targets):
                    found[node.lineno] = f"sets it on actions alone, not on {module}"
            elif isinstance(node, ast.ImportFrom) and node.module == "actions" and any(a.name in names for a in node.names):
                found[node.lineno] = "from actions import"
    return [f"{path_name}:{i}: {why}: {lines[i - 1].strip()}" for i, why in sorted(found.items())]


def pointers(root, new_module):
    """"path:line: why: text" of each line naming actions.py in the docstring of an agent module the new module (its
    text) imports (`luxcavation.py: actions.py reads the Luxcavation pages`): it may now point at the new module."""
    found = []
    for node in ast.parse(new_module).body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or ""]
            for name in names:
                path = root / "agent" / f"{name}.py"
                if name == "actions" or not path.exists():
                    continue
                body = ast.parse(text := read(path)).body
                if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                    lines = split_lines(text)
                    found += [f"agent/{name}.py:{i}: points at actions.py: {lines[i - 1].strip()}"
                              for i in range(body[0].lineno, body[0].end_lineno + 1) if "actions.py" in lines[i - 1]]
    return found


def read(path):
    return path.read_bytes().decode("utf-8")


def write(path, text):
    path.write_bytes(text.encode("utf-8"))  # as read: no newline translation


def split(root, module, modules=MODULES, stay=STAY):
    """Move module's names out of root/agent/actions.py and point the tests and tools at them; a Report. Misfit, with
    nothing written, when the table does not fit."""
    module = Path(module).stem
    if module not in modules:
        raise Misfit(f"{module} is not in the table: one of {', '.join(modules)}")
    agent = root / "agent"
    if (agent / f"{module}.py").exists():
        raise Misfit(f"agent/{module}.py exists already")
    src = Source(read(agent / "actions.py"))
    plan = move_plan(src, module, modules, stay)
    if plan.problems:
        raise Misfit("\n".join(plan.problems))
    new_module, from_actions, imports = module_text(src, plan, modules[module][0])
    new_actions, dropped = actions_text(src, plan)
    names = plan.out | (dropped & imports)  # what the tests read through the module from now on
    shared = from_actions | (imports - dropped)  # what actions and the module both bind
    new_main = main_text(read(agent / "main.py"), module)
    files, renamed, hand = {}, {}, []
    for path in sorted([*root.glob("tests/*.py"), *root.glob("tools/*.py"), *root.glob("tools/live/*.py")]):
        rel = path.relative_to(root).as_posix()
        if rel in OWN:
            continue
        new, count = rename(read(path), module, names)
        hand += by_hand(rel, new, names, module, shared)
        if count:
            files[path], renamed[rel] = new, count
    for path in sorted([*agent.glob("*.py"), *root.glob("docs/**/*.md"), *root.glob("*.md")]):
        if path.name not in ("actions.py", f"{module}.py"):
            hand += by_hand(path.relative_to(root).as_posix(), read(path), names, module)
    hand += pointers(root, new_module)
    write(agent / f"{module}.py", new_module)
    write(agent / "actions.py", new_actions)
    write(agent / "main.py", new_main)
    for path, new in files.items():
        write(path, new)
    return Report([n for s in plan.moved for n in s.names], renamed, hand)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")  # comments hold CJK; a redirected Windows console is cp950
    try:
        report = split(ROOT, sys.argv[1])
    except Misfit as e:
        print(f"the table does not fit agent/actions.py; nothing written:\n{e}")
        sys.exit(1)
    print(f"moved {len(report.moved)} names to agent/{Path(sys.argv[1]).stem}.py: {', '.join(report.moved)}")
    print(f"renamed {sum(report.renamed.values())} reads in {len(report.renamed)} files:")
    for path, count in report.renamed.items():
        print(f"  {path}: {count}")
    print(f"== {len(report.by_hand)} to edit by hand")
    for line in report.by_hand:
        print(line)


if __name__ == "__main__":
    main()
