# Driving the settings GUI with cua-driver

What `cua-driver` needs to operate the Tauri settings app (`gui/`) on Windows. Each fact names its source: `[run]` is the run of 2026-10-30 with `cua-driver 0.38.0` on Windows 11, `[second run]` a later run that day on the same setup (a check of the guard-turns note), `[third run]` a run of 2026-10-31 on the same setup (a check of the trial notes and the teams tab), `[cua docs]` the installed cua-driver skill (`~/.claude/skills/cua-driver/`) or `cua-driver describe <tool>`, `[retro]` a finding of the 2026-10-30 retro over agent sessions of 2026-10-16 and 2026-10-17, `[devtools run]` the run of 2026-11-14 that built `tools/gui_devtools.mjs` (#747; WebView2 157.0.4341.46, Windows 11, display at 150 %), `[#745 run]` the check of PR #745 the same day. The `maalc-gui-check` skill is the procedure; this file is what it relies on.

## cua or DevTools

Two ways act on the window, and they prove different things:

- **cua-driver, background delivery**: what a user's click, typing, select or scroll does. Its input goes to the window through Windows, as a user's would, and leaves the user's cursor and focused window alone. Use it for every control a user clicks.
- **`tools/gui_devtools.mjs`**, over the page's DevTools port: what cua's background delivery cannot do. A press held for a time, a drag-and-drop, keys with modifiers (Shift+Tab), the light or dark scheme, the page at another size (800 × 480), an element's box, a still of the page with the header's path blacked out, the accessibility node, the console. Its input enters the page (Chromium's own input path), not the window: it never touches the user's cursor, and it does not prove what the window itself does (its frame, the title bar's drag region, a system key such as Alt+F4 closing it).

A cua click on a tab (the pixels come from the latest `get_window_state` screenshot):

    cua-driver call click '{"pid":<pid>,"window_id":<hwnd>,"x":316,"y":116,"delivery_mode":"background","session":"<task>"}'

The same window over DevTools: `open` holds it in the background and prints `{"pid", "hwnd", "port", ...}`, then each command acts on the page at that port (`--help` lists them all):

    node tools/gui_devtools.mjs open --root <main checkout>/.local/scratch/<task>/gui-root     (a background command)
    node tools/gui_devtools.mjs drag "js:[...document.querySelectorAll('aside li')][0]" "js:[...document.querySelectorAll('aside li')][1]" --port <port> --then "document.querySelector('header').innerText"

What the run of `tools/gui_devtools.mjs` showed:

- The app reads `WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS` and `WEBVIEW2_USER_DATA_FOLDER`: the browser process ran with Tauri's own `--disable-features=msWebOOUI,msPdfOOUI,msSmartScreenProtection` and the added `--remote-debugging-port`, on the root's `webview2` folder. A data folder of its own keeps the port from being lost to another WebView2 of the same app. [devtools run: the command line of `msedgewebview2.exe`]
- The `hwnd` that `open` prints is cua's `window_id`. [devtools run: `list_windows`]
- `--viewport 800x480` lays the page out as a real 800 × 480 window does: the team page and the 星光方案 tab scrolled to the second row of cards gave #745's numbers to the hundredth of a pixel, which came from the window resized with cua's `set_window_frame` (1204 × 724 at 150 %, `innerWidth` 800, `innerHeight` 480). A cua still taken meanwhile shows the page drawn at the window's top left and the rest blank. [devtools run; #745 run]
- An emulation (scheme, viewport, forced `:hover`) lasts while its DevTools session is open, and other sessions see it: `scheme light --viewport 800x480` left in the background made a second command read 800 × 480 and the light scheme, and a cua still showed it; stopping it brought back 1500 × 860, dark. [devtools run]
- Stopping the `open` command (a background task's stop, `taskkill`) ended the app and its WebView2 with it: libuv puts a child that is not detached in a job killed with its parent (`src/win/process.c`), and the WebView2 processes ended with their app. The app's own close button ended the `open` command. An app that `tools/gui_probe.py` had left on the root was stopped by the next `open` there. [devtools run]
- A DevTools drag intercepts Chromium's drag (`Input.setInterceptDrags`) and dispatches the drag events at the target, so the page's hit testing picks where it lands; it does not go through Windows' drag-and-drop, which a Tauri setting broke once (`dragDropEnabled`, #64): a build with `"dragDropEnabled": true` still reordered the team list under a DevTools drag. That setting stays covered by `gui/src/dragSort.test.ts`. [devtools run]

## Build and launch

- The GUI has its own lockfile: `pnpm --dir gui install --frozen-lockfile` before the first build in a worktree (`docs/agents/local-dev.md` "New worktree" installs only the root's). `pnpm --dir gui tauri build --no-bundle` takes about 3 minutes cold and writes `gui/src-tauri/target/release/maalc-gui.exe`. [run]
- The exe reads and writes `<folder of the exe>/config/settings.json` and looks for `resource/` or `assets/resource/` beside it (`gui/src-tauri/src/lib.rs`, `root` and `load_theme_packs`). Launching it from `target/release/` finds neither, and launching it from `install/` edits the real settings. `tools/gui_probe.py` copies the exe into a throwaway folder with demo settings and a link to `assets/`. [lib.rs]
- The demo settings are the `valid` case of `tests/settings_cases.json` (`language` is `zh_tw`; a retro report notes that `en` is not a valid value and `en_us` is). [run; retro, 2026-10-17]
- The window title is `maalc` (`gui/src-tauri/tauri.conf.json`, `app.windows[0].title`), and it is the top-level window of the exe's own pid, so `tools/gui_probe.py` finds it by pid and title. [run]
- The header of the app shows the full path of `settings.json`, a local path. Black it out of every screenshot before it is attached to a public issue or PR. [run: visible in the first screenshot]
- Stop the app by the pid the probe printed: `taskkill /T /F /PID <pid>` (PowerShell; Git Bash rewrites `/T` into a path). The process has WebView2 children, so `/T` is needed. cua's `kill_app` was refused in standard permission mode. [run; retro]

## Seeing the window

- `get_window_state` with `include_accessibility_tree:false` returns a screenshot of that one window plus its bounds; `--screenshot-out-file <png>` on `cua-driver call` saves it. It never captures the screen. `get_desktop_state` captures the whole display: not for a GUI check. [run; cua docs `describe get_window_state`]
- Sizes differ by setup: the window is 1500x860 in `tauri.conf.json` (1100x760 before #732, 1500x760 before #741); in the [run], `list_windows` reported 1654x1187 and the screenshot was 1455x1044. Action coordinates are pixels of the latest screenshot, not window or screen pixels. A retro report names 1620x1500 for another setup: read the sizes again each run. [run; retro]
- Each `cua-driver call` is a session of its own. A `drag` or `click` needs a `get_window_state` of the same window in the same session first, else it fails with `screenshot_context_missing` / `window_never_read`. Pass the same `"session":"<name>"` to every call (read, then act, then read), or put the steps in one `run_script`. [run]
- The page is a WebView2: the first tree read showed only the title bar (5 elements), a later one 138 elements with a `Document` node. Act by pixel off the screenshot and judge by the next screenshot. [run]

## Input

- Background delivery is the default and the cua docs ask to try it first; the driver says by `background_unavailable` when it cannot. [cua docs `describe drag`, WINDOWS.md "Always try `delivery_mode:"background"` first"] Two retro sessions got `Background delivery is not available for target window class 'Tauri Window'` for `mouse_scroll`, and fixed it with `delivery_mode:"foreground"`. [retro, 2026-10-16]
- A click on a tab went through in background mode. [run]
- A drag reported `effect: "unverifiable"` every time, whether the list moved or not: only the next screenshot tells. [run]
- Drag-and-drop that moved: `delivery_mode:"foreground"`, `duration_ms:4000`, `steps:120`, on the team list in the left column (Team a dragged below Team b; both swapped, "有未儲存的變更" appeared). The retro report says a 1 s drag fired the events but did not reorder (not repeated here). A drag of 1 s with 20 steps in background mode on a deployment card did nothing: those cards are click-to-order, not draggable. No background drag has been tried on a sortable list yet; background delivery answers `background_unavailable` for event kinds it knows it drops, Chromium DOM mouse among them, and the page is a WebView2 (Chromium), so expect that answer for a drag. The foreground drag above came before the user's yes was needed for it (next point). [run; retro, 2026-10-17; cua docs WINDOWS.md `delivery_mode`]
- Foreground delivery is SendInput with a brief `SetForegroundWindow`: it can move the physical cursor and fronts the window for the length of the action, and restoring the previous foreground is best-effort. It takes the cursor from whoever is using the machine, so the `maalc-gui-check` skill runs it only on the user's yes to that action (the user, 2026-11-08). [cua docs WINDOWS.md `delivery_mode`, RUNTIME.md "Foreground boundary"]
- Scrolling the settings page did not work in a second run on 2026-10-30 (cua-driver 0.38.0, Teams tab, to reach the note under the guard-turns field): `scroll` of 10 ticks in background delivery and 15 in foreground, `press_key end` after a background click on the page, and a foreground `drag` of the page's scrollbar; after each, the next screenshot showed the page still at its top. This differs from the retro report above, where foreground delivery fixed `mouse_scroll`. Resizing the window with `SetWindowPos` without activating it left the WebView2 area blank, and the app was restarted. That run could not look at a control below the fold. [second run]
- What does scroll the page: a background `click` on the page's scrollbar track, at the right edge of the screenshot (x 1443 of 1455), pages down below the thumb and up above it; a click on the arrow at either end moves a few lines. A run on 2026-10-31 (cua-driver 0.38.0, Teams tab) reached the bottom of a team and came back to the top this way, after `scroll` in background (`background_unavailable`), `scroll` in foreground and Ctrl+minus in foreground had left the page where it was. [third run]
- A `<select>` changes in background delivery: a `click` on it focuses it, then `press_key` `escape` and `up` / `down` step to the next option, and the next screenshot shows it (the heal method and the language select, 2026-10-31). [third run]
- A drag, a held press or a key with modifiers that background delivery cannot send goes through `tools/gui_devtools.mjs` ("cua or DevTools" above), not foreground delivery. A team dragged onto the next one there reordered the list and showed "有未儲存的變更"; a press on a team moved 40 px while held reported the drag the page started and cancelled it. [devtools run]
- `set_window_frame` resized the window to 800 × 480 logical (1204 × 724 at 150 %) and the page stayed drawn, unlike the `SetWindowPos` above; `gui_devtools.mjs --viewport 800x480` gives the same layout without resizing the window. [#745 run; devtools run]
- Which controls take a drag: the sortable lists (`gui/src/ui.tsx`, `li draggable`) and the theme pack chips (`gui/src/ThemePacks.tsx`). The setting that breaks them is `dragDropEnabled`: Tauri's default swallows HTML5 drag-and-drop on Windows, so it stays `false` in `tauri.conf.json` (commit 380aad8, #64). [git log 380aad8; retro]

## UIPI and elevation

A process at a higher integrity level than the driver refuses its input: AALC self-elevates through `pyuac`, and cua reported `UIPI: target hwnd … is at High integrity`. The settings GUI launched by `tools/gui_probe.py` runs at the integrity of the shell that launched it and took input in the run above; if a future shell is elevated and the driver is not, expect the same refusal. [retro, 2026-10-16; run for the GUI]
