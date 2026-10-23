// The gift list tab (spec 04 section 13; #291, #295): pick a list, pick a state, click gifts to give them that state.
// Parts, for the tickets that build on it: the top bar (list choice, fusion condition) and the apply bar (the state a click
// applies) below, KeywordTabs and KeywordPanel (KeywordGrid.tsx; its GiftTile is what a hover popover attaches to), all reading
// GiftEdit (giftEdit.ts) for the list being shown, the picked state, and `apply`/`flash`.
import { useEffect, useRef, useState } from "react";
import "./giftlists.css";
import { GIFT_BY_ID, giftName } from "./giftCatalog";
import { plan, setState, GiftEditContext, type GiftEdit } from "./giftEdit";
import { DEFAULT_LIST, type GiftState } from "./gifts";
import { fill } from "./i18n";
import { FUSION_CONDITIONS, GIFT_KEYWORDS } from "./model";
import { GiftListOptions } from "./GiftListOptions";
import { KeywordPanel, KeywordTabs } from "./KeywordGrid";
import { useEditor } from "./ui";

const STATES: GiftState[] = ["want", "keep", "drop"];
const FLASH_MS = 4200;

export function GiftListsTab() {
  const { s, update, t, tv } = useEditor();
  // What is being edited is UI state, not saved: "default" (the data file's list, read-only) or the id of one of the user's lists.
  const [chosen, setChosen] = useState("default");
  const [pick, setPick] = useState<GiftState>("want");
  const [tab, setTab] = useState(GIFT_KEYWORDS[0]);
  const [message, setMessage] = useState({ text: "", warn: false });
  const timer = useRef<number>(undefined);
  useEffect(() => () => clearTimeout(timer.current), []);

  const at = s.gift_lists.findIndex((l) => l.id === chosen);
  const readOnly = at < 0; // also when the chosen list is gone (deleted): back to the default, and the select says so
  const shownId = readOnly ? "default" : chosen;
  const list = readOnly ? DEFAULT_LIST : s.gift_lists[at];
  const zh = s.language === "zh_tw";

  const flash = (text: string, warn = false) => {
    setMessage({ text, warn });
    clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage({ text: "", warn: false }), FLASH_MS);
  };
  /** True when the list can change; otherwise shows why not. */
  const editable = () => { if (readOnly) flash(t("gl.ro"), true); return !readOnly; };

  const apply = (id: number, to = pick) => {
    if (!editable()) return;
    const name = giftName(GIFT_BY_ID.get(id)!, zh), result = plan(list, id, to);
    if ("locked" in result) {
      const by = result.locked.map((b) => giftName(GIFT_BY_ID.get(b)!, zh)).join(t("gl.sep"));
      return flash(fill(t("gl.lock_why"), { name, by }), true);
    }
    update((d) => setState(d.gift_lists[at], id, result.to));
    if (result.downgraded) flash(fill(t("gl.unbuyable_keep"), { name }), true);
    else setMessage({ text: "", warn: false });
  };
  const edit: GiftEdit = { list, readOnly, pick, apply, flash };

  // 1, 2 and 3 pick the state, unless the user is typing or choosing in a field.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const state = STATES[Number(e.key) - 1];
      if (!state || e.ctrlKey || e.metaKey || e.altKey || (e.target as HTMLElement).closest("input, select, textarea")) return;
      setPick(state);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const empty = !readOnly && !list.want.length && !list.keep.length;
  const startFromDefault = () => update((d) => {
    const { order, want, keep, gorder, fusion_condition } = structuredClone(DEFAULT_LIST);
    Object.assign(d.gift_lists[at], { order, want, keep, gorder, fusion_condition });
  });

  return (
    <GiftEditContext.Provider value={edit}>
      <div className="gl">
        <div className="gl-top">
          <div className="gl-bar">
            <label>{t("gl.list")}{" "}
              <select value={shownId} onChange={(e) => setChosen(e.target.value)}>
                <option value="default">{t("defaultPlanLocked")}</option>
                {s.gift_lists.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </select>
            </label>
            <GiftListOptions at={at} readOnly={readOnly} choose={setChosen} flash={flash} />
            {/* #307: search and help at the end of the bar. */}
            {readOnly && <span className="gl-readonly">{t("gl.readonly")}</span>}
            <span className="spacer" />
            <label title={t("team.fusion_condition_note")}>{t("team.fusion_condition")}{" "}
              <select value={list.fusion_condition}
                onChange={(e) => editable() && update((d) => { d.gift_lists[at].fusion_condition = e.target.value; })}>
                {FUSION_CONDITIONS.map((v) => <option key={v} value={v}>{tv("fusion_condition", v)}</option>)}
              </select>
            </label>
          </div>
          <div className="gl-apply">
            <div className="gl-pick" role="radiogroup" aria-label={t("gl.apply")} onKeyDown={(e) => {
              const step = { ArrowRight: 1, ArrowDown: 1, ArrowLeft: -1, ArrowUp: -1 }[e.key];
              if (!step) return;
              e.preventDefault();
              const next = (STATES.indexOf(pick) + step + STATES.length) % STATES.length;
              setPick(STATES[next]);
              e.currentTarget.querySelectorAll<HTMLElement>("[role=radio]")[next].focus();
            }}>
              <span className="gl-label">{t("gl.apply")}</span>
              {STATES.map((v, i) => (
                <button type="button" key={v} role="radio" aria-checked={pick === v} aria-keyshortcuts={String(i + 1)} tabIndex={pick === v ? 0 : -1}
                  className={`gl-state ${v}${pick === v ? " on" : ""}`} onClick={() => setPick(v)}>
                  <i aria-hidden />{t(`state.${v}`)}<kbd aria-hidden>{i + 1}</kbd>
                </button>
              ))}
            </div>
            <span className="gl-hint">{t("gl.hint")}</span>
            {/* #296: the "purchase order" button goes at the end of this row. */}
          </div>
          <div className={"gl-flash" + (message.warn ? " warn" : "")} role="status" aria-live="polite">{message.text}</div>
        </div>
        <KeywordTabs tab={tab} onTab={setTab} />
        <section className="gl-panel" id="gl-panel" role="tabpanel" aria-labelledby={`gl-tab-${tab}`}>
          {empty && (
            <div className="gl-empty">
              <b>{t("gl.empty")}</b>
              <p>{t("gl.empty_note")}</p>
              <button type="button" onClick={startFromDefault}>{t("gl.from_default")}</button>
            </div>
          )}
          <KeywordPanel keyword={tab} />
        </section>
      </div>
    </GiftEditContext.Provider>
  );
}
