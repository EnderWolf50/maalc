# Driving the settings GUI with cua-driver

What `cua-driver` needs to operate the Tauri settings app (`gui/`) on this machine. Each fact names its source: `[run]` is the run of 2026-10-30 with `cua-driver 0.38.0` on the user's Windows 11 machine, `[second run]` a later run that day on the same machine (a check of the guard-turns note), `[cua docs]` the installed cua-driver skill (`~/.claude/skills/cua-driver/`) or `cua-driver describe <tool>`, `[retro]` a session report of the 2026-10-30 retro (kept on one machine; the agent sessions it names ran 2026-10-16 and 2026-10-17). The `maalc-gui-check` skill is the procedure; this file is what it relies on.

## Build and launch

- The GUI has its own lockfile: `pnpm --dir gui install --frozen-lockfile` before the first build in a worktree (`docs/agents/local-dev.md` "New worktree" installs only the root's). `pnpm --dir gui tauri build --no-bundle` takes about 3 minutes cold and writes `gui/src-tauri/target/release/maalc-gui.exe`. [run]
- The exe reads and writes `<folder of the exe>/config/settings.json` and looks for `resource/` or `assets/resource/` beside it (`gui/src-tauri/src/lib.rs`, `root` and `load_theme_packs`). Launching it from `target/release/` finds neither, and launching it from `install/` edits the real settings. `tools/gui_probe.py` copies the exe into a throwaway folder with demo settings and a link to `assets/`. [lib.rs]
- The demo settings are the `valid` case of `tests/settings_cases.json` (`language` is `zh_tw`; a retro report notes that `en` is not a valid value and `en_us` is). [run; retro batch2 agent a29be6e4, 10-17]
- The window title is `maalc` (`gui/src-tauri/tauri.conf.json`, `app.windows[0].title`), and it is the top-level window of the exe's own pid, so `tools/gui_probe.py` finds it by pid and title. [run]
- The header of the app shows the full path of `settings.json`, a local path. Black it out of every screenshot before it is attached to a public issue or PR. [run: visible in the first screenshot]
- Stop the app by the pid the probe printed: `taskkill /T /F /PID <pid>` (PowerShell; Git Bash rewrites `/T` into a path). The process has WebView2 children, so `/T` is needed. cua's `kill_app` was refused in standard permission mode. [run; retro batch4 agent af5cf]

## Seeing the window

- `get_window_state` with `include_accessibility_tree:false` returns a screenshot of that one window plus its bounds; `--screenshot-out-file <png>` on `cua-driver call` saves it. It never captures the screen. `get_desktop_state` captures the whole display: not for a GUI check. [run; cua docs `describe get_window_state`]
- Sizes on this machine: the window is 1100x760 in `tauri.conf.json`, `list_windows` reports 1654x1187 and the screenshot is 1455x1044. Action coordinates are pixels of the latest screenshot, not window or screen pixels. A retro report names 1620x1500 for another setup: read the sizes again each run. [run; retro batch4]
- Each `cua-driver call` is a session of its own. A `drag` or `click` needs a `get_window_state` of the same window in the same session first, else it fails with `screenshot_context_missing` / `window_never_read`. Pass the same `"session":"<name>"` to every call (read, then act, then read), or put the steps in one `run_script`. [run]
- The page is a WebView2: the first tree read showed only the title bar (5 elements), a later one 138 elements with a `Document` node. Act by pixel off the screenshot and judge by the next screenshot. [run]

## Input

- Background delivery is the default and the cua docs ask to try it first; the driver says by `background_unavailable` when it cannot. [cua docs `describe drag`, WINDOWS.md "Always try `delivery_mode:"background"` first"] Two retro sessions got `Background delivery is not available for target window class 'Tauri Window'` for `mouse_scroll`, and fixed it with `delivery_mode:"foreground"`. [retro batch4, agents af5cf and a2ebe, 10-16]
- A click on a tab went through in background mode. [run]
- A drag reported `effect: "unverifiable"` every time, whether the list moved or not: only the next screenshot tells. [run]
- Drag-and-drop that moved: `delivery_mode:"foreground"`, `duration_ms:4000`, `steps:120`, on the team list in the left column (Team a dragged below Team b; both swapped, "有未儲存的變更" appeared). The retro report says a 1 s drag fired the events but did not reorder (not repeated here). A drag of 1 s with 20 steps in background mode on a deployment card did nothing: those cards are click-to-order, not draggable. [run; retro batch2 agent a29be6e4, 10-17]
- Foreground delivery raises the window for the length of the action and then restores the previous foreground; it needs the user's go-ahead for visible control (cua rule 4), which the brief of the check gives. [cua docs WINDOWS.md; SKILL.md "Rules" 4]
- Scrolling the settings page did not work in a second run on 2026-10-30 (cua-driver 0.38.0, Teams tab, to reach the note under the guard-turns field): `scroll` of 10 ticks in background delivery and 15 in foreground, `press_key end` after a background click on the page, and a foreground `drag` of the page's scrollbar; after each, the next screenshot showed the page still at its top. This differs from the retro report above, where foreground delivery fixed `mouse_scroll`. Resizing the window with `SetWindowPos` without activating it left the WebView2 area blank, and the app was restarted. That run could not look at a control below the fold; until another way is found, a check that cannot reach one says so in its report. [second run]
- Which controls take a drag: the sortable lists (`gui/src/ui.tsx`, `li draggable`) and the plan chips (`gui/src/Plans.tsx`). The setting that breaks them is `dragDropEnabled`: Tauri's default swallows HTML5 drag-and-drop on Windows, so it stays `false` in `tauri.conf.json` (commit 380aad8, #64). [git log 380aad8; retro batch2]

## UIPI and elevation

A process at a higher integrity level than the driver refuses its input: AALC self-elevates through `pyuac`, and cua reported `UIPI: target hwnd … is at High integrity`. The settings GUI launched by `tools/gui_probe.py` runs at the integrity of the shell that launched it and took input in the run above; if a future shell is elevated and the driver is not, expect the same refusal. [retro batch4, agent af5cf, 10-16T07:02; run for the GUI]
