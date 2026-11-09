# PR bodies and comments

Every number is copied from command output in this session, and every "verified" points at the command or clip that shows it. Evidence follows AGENTS.md "Public repo": attach files with `--attach '<file>#<alt>'` (`gh pr create`, `gh pr comment`, `gh issue comment`). Alt text is for images only: a video attached with `#<alt>` fails with `cannot set alt text on video` (seen 2026-10-27), so attach a video without `#<alt>`.

## Language

Issues, PRs and every comment on them are written in Traditional Chinese, titles and bodies alike: the user reads them, and a body that switches language is hard to follow (the user, 2026-11-08). The templates below are already in Chinese. What a reader copies or searches, or a tool parses, keeps its form:

- code names, file paths, `file:line`, commands, quoted log lines and dialog text, links, numbers;
- the game's own words for its screens, buttons and items, as `GLOSSARY.md` spells them (Give Up, Cost, Hidden Battle);
- GitHub's closing keywords (`Closes #<n>`, `Fixes #<n>`, `Resolves #<n>`, in any form) and the linking ones (`Refs #<n>`, `Part of #<n>`);
- a PR title's Conventional Commits prefix, followed by Chinese: `fix(map): 第 5 層商店不再重複點擊`;
- the keys of the 驗證 template (`Tests:`, `Live:`, `Acceptance:`, `Fixtures:`); `public-text-guard.py` reads the counts `N passed, M failed`, `Tests: none (docs only)`, and `not run` with its issue;
- a map issue's `Notes` and `Decisions so far` headings, which the `wayfinder` skill looks up: in parentheses after the Chinese, `## 目前的決定（Decisions so far）`.

Commit messages stay English (the user confirmed it, 2026-11-08), and carry no closing keyword: a `fix: #387` subject closed #387 when its PR merged although the PR body said `Refs #387` (#602). Whether an issue closes goes in the PR body; a commit writes `review(#N): ...` or `Refs #N`, and `tools/review_lint.py` flags the rest.

The `pr` skill's headings in Chinese: 為什麼, 摘要, 範圍, 取捨, 證據 (**之前：** / **之後：**), 合併風險 (**門：** 單向 / 雙向, **影響範圍：**).

An open issue or PR found in English is rewritten in place, its meaning, links, tables and `file:line` unchanged: save the old body, write the new one, `gh issue edit <n>` or `gh pr edit <n>` with `--title` and `--body-file`. `uv run python tools/rewrite_check.py <old> <new>` names each code span, link, reference or number the rewrite dropped, and lists the English words left for you to judge. Done when it prints no `dropped` line.

## PR body

The `pr` skill's sections, then:

```markdown
## 驗證

- Tests: `<指令>` → `<passed> passed, <failed> failed`，有跳過時加 `, <skipped> skipped`（只改文件的 PR 改寫 `Tests: none (docs only)`）
- Live: <在模擬器上跑過的路徑>；not run: <沒跑的路徑>，各附追蹤它的 issue
- Acceptance: `<issue 的驗收條件>` → 達成／未達成，附數字
- Fixtures: 實際截圖，或合成圖（檔名以 `.synthetic.png` 結尾）
```

An issue the PR finishes only in part gets its body rewritten in the same session (`docs/agents/issue-tracker.md` "Keeping issues current").

`public-text-guard.py` denies `gh pr create|edit --body-file` when the body has neither `N passed, M failed[, K skipped]` nor `Tests: none (docs only)`, or a line saying `not run` names no issue (`#<n>`; `not run: none` passes).

## Comments

Post with `gh pr comment <n>` or `gh issue comment <n>`; a multi-line body follows `docs/agents/issue-tracker.md` (Create an issue). An issue is referenced as `#<n>` or `Refs #<n>`.

Live-test evidence, with the verdicts of the `maalc-live-test` skill's Report step and each clip attached:

```markdown
**實機測試**（<short SHA>）：<跑了什麼>

- <檢查項>：通過／失敗／沒走到（<clip>）
- Acceptance: `<驗收條件>` → 達成／未達成
```

Review-fix reply, one per finding, on its thread: `gh api repos/{owner}/{repo}/pulls/<n>/comments/<id>/replies -f body='<one line>'`, or `-F body=@<absolute path>` for more lines:

```markdown
已在 <short SHA> 修正：<改了什麼，一行>
<或：沒有改：<理由>>
```

Status update; on an issue a PR covers in part, it names what remains:

```markdown
**狀態**：<完成／進行中／卡住>

- 完成：<項目>（#<PR>）
- 下一步：<項目>
- 卡在：<誰或什麼>，自 <日期> 起
```
