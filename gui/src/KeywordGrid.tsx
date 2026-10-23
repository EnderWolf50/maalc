// The gift list tab's keyword tabs and the grid of one keyword: tier blocks of icon tiles, one tile per gift.
import { useRef, useState, type KeyboardEvent } from "react";
import { GIFT_BY_ID, giftName, iconUrl, tiersOf } from "./giftCatalog";
import { useGiftEdit } from "./giftEdit";
import { effective, mainKeyword, state, type GiftState, type ListRules } from "./gifts";
import { fill, type Key } from "./i18n";
import { GIFT_KEYWORDS } from "./model";
import { useEditor } from "./ui";

const TIERS = ["", "I", "II", "III", "IV", "V"];
// The keyword colours of the mockup; a dot stands in for the keyword icon, which the repo has no art for.
const KEYWORD_COLOR: Record<string, string> = {
  Bleed: "#bc1b1f", Blunt: "#99704e", Burn: "#db213f", Charge: "#0dbed7", Pierce: "#926a46", Poise: "#67a8a8", Rupture: "#15d0ae",
  Sinking: "#1e77e9", Slash: "#9b7351", Tremor: "#fb9e23", Keywordless: "#7a8194",
};
const kwText = (k: string) => `kw.${k}` as Key;

/** What the list makes of a gift for display: its effective state, and whether a wanted fusion locks it (shown kept). */
export function look(list: ListRules, id: number): { shown: GiftState; locked: boolean } {
  const shown = effective(list, id);
  return { shown, locked: shown === "keep" && state(list, id) === "drop" };
}

/** What a keyword has set: wanted and kept gifts, wanted fusion gifts. */
function counts(list: ListRules, keyword: string) {
  const c = { want: 0, keep: 0, fusion: 0 };
  for (const { ids } of tiersOf(list.gorder, keyword)) {
    for (const id of ids) {
      const { shown } = look(list, id);
      if (shown === "drop") continue;
      if (shown === "want" && GIFT_BY_ID.get(id)!.kind === "fusion") c.fusion++;
      else c[shown]++;
    }
  }
  return c;
}

/** The keyword tabs, in the game's order; arrow keys switch. */
export function KeywordTabs({ tab, onTab }: { tab: string; onTab: (k: string) => void }) {
  const { t } = useEditor();
  const { list } = useGiftEdit();
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const move = (e: KeyboardEvent) => {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    const next = GIFT_KEYWORDS[GIFT_KEYWORDS.indexOf(tab) + step];
    if (!step || !next) return;
    e.preventDefault();
    onTab(next);
    refs.current[next]?.focus();
  };
  return (
    <div className="gl-tabs" role="tablist" aria-label={t("gl.tabs")} onKeyDown={move}>
      {GIFT_KEYWORDS.map((k) => {
        const c = counts(list, k), n = c.want + c.keep + c.fusion, on = k === tab;
        return (
          <button type="button" key={k} id={`gl-tab-${k}`} role="tab" aria-selected={on} aria-controls="gl-panel" tabIndex={on ? 0 : -1}
            className={"gl-tab" + (on ? " on" : "")} ref={(el) => { refs.current[k] = el; }} onClick={() => onTab(k)}>
            <i className="gl-dot" style={{ background: KEYWORD_COLOR[k] }} aria-hidden />
            <span>{t(kwText(k))}</span>
            {n > 0 && <b className="gl-n" title={fill(t("gl.tier_set"), { n })}>{n}</b>}
          </button>
        );
      })}
    </div>
  );
}

/** One keyword's header and its tier blocks. Roving tabindex: one tile is the tab stop; the arrow keys move between tiles. */
export function KeywordPanel({ keyword }: { keyword: string }) {
  const { s, t } = useEditor();
  const { list } = useGiftEdit();
  const grid = useRef<HTMLDivElement>(null);
  const [focused, setFocused] = useState<number | null>(null);
  const zh = s.language === "zh_tw";
  const c = counts(list, keyword), blocks = tiersOf(list.gorder, keyword);
  const stop = focused !== null && GIFT_BY_ID.get(focused)?.keyword === keyword ? focused : blocks[0]?.ids[0];

  const walk = (e: KeyboardEvent) => {
    if (!e.key.startsWith("Arrow")) return;
    const tiles = [...grid.current!.querySelectorAll<HTMLElement>("[data-gift]")];
    const i = tiles.indexOf(e.target as HTMLElement);
    if (i < 0) return;
    let next: HTMLElement | undefined;
    if (e.key === "ArrowLeft") next = tiles[i - 1];
    else if (e.key === "ArrowRight") next = tiles[i + 1];
    else {
      // The nearest tile in the row above or below, the one closest across.
      const from = tiles[i].getBoundingClientRect(), dir = e.key === "ArrowDown" ? 1 : -1;
      const rows = tiles.filter((x) => dir * (x.getBoundingClientRect().top - from.top) > 8);
      const near = Math.min(...rows.map((x) => Math.abs(x.getBoundingClientRect().top - from.top)));
      next = rows.filter((x) => Math.abs(x.getBoundingClientRect().top - from.top) - near < 8)
        .sort((a, b) => Math.abs(a.getBoundingClientRect().left - from.left) - Math.abs(b.getBoundingClientRect().left - from.left))[0];
    }
    if (next) { e.preventDefault(); next.focus(); }
  };

  return (
    <div ref={grid} onKeyDown={walk}>
      <h3 className="gl-kwh">
        <i className="gl-dot big" style={{ background: KEYWORD_COLOR[keyword] }} aria-hidden />
        <b>{t(kwText(keyword))}</b>{zh && keyword !== "Keywordless" && <small>{keyword}</small>}
        {keyword === mainKeyword(list) && <span className="gl-tag main">{t("gl.main")}</span>}
        <span className="gl-tag">{fill(t("gl.rank"), { n: list.order.indexOf(keyword) + 1 })}</span>
        {c.want > 0 && <span className="gl-tag want">{fill(t("gl.n_want"), { n: c.want })}</span>}
        {c.keep > 0 && <span className="gl-tag keep">{fill(t("gl.n_keep"), { n: c.keep })}</span>}
        {c.fusion > 0 && <span className="gl-tag fusion">{fill(t("gl.n_fusion"), { n: c.fusion })}</span>}
      </h3>
      {blocks.map(({ tier, ids }) => {
        const kinds = ids.map((id) => GIFT_BY_ID.get(id)!.kind);
        const set = ids.filter((id) => look(list, id).shown !== "drop").length;
        const note = kinds.includes("fusion") ? t("gl.tier_fusion") : kinds.some((k) => k === "material" || k === "vestige") ? t("gl.tier_unbuyable") : "";
        return (
          <section key={tier} className="gl-tier" aria-label={TIERS[tier]}>
            <h4><span className={"gl-tierno" + (tier >= 4 ? " fusion" : "")}>{TIERS[tier]}</span>
              <small>{note && `${note}・`}{fill(t("gl.tier_n"), { n: ids.length })}{set > 0 && `・${fill(t("gl.tier_set"), { n: set })}`}</small></h4>
            <div className="gl-wall">
              {ids.map((id) => <GiftTile key={id} id={id} zh={zh} tabStop={id === stop} onFocus={() => setFocused(id)} />)}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/** One gift: its icon in a frame that shows its state (want thick and striped, keep solid, drop faded, locked dashed with a padlock). */
function GiftTile({ id, zh, tabStop, onFocus }: { id: number; zh: boolean; tabStop: boolean; onFocus: () => void }) {
  const { t } = useEditor();
  const { list, apply } = useGiftEdit();
  const g = GIFT_BY_ID.get(id)!;
  const { shown, locked } = look(list, id);
  const label = fill(t("gl.tile"), { name: giftName(g, zh), tier: TIERS[g.tier], state: t(`state.${shown}`), lock: locked ? t("gl.locked") : "" });
  return (
    <button type="button" className={`gl-tile ${shown}${locked ? " locked" : ""}`} aria-label={label} data-gift={id} tabIndex={tabStop ? 0 : -1}
      onFocus={onFocus} onClick={() => apply(id)}>
      <img src={iconUrl(id)} alt="" loading="lazy" />
      {locked && (
        <svg className="gl-lock" viewBox="0 0 16 16" aria-hidden><path d="M5 7V5a3 3 0 016 0v2h1v7H4V7zm1.5 0h3V5a1.5 1.5 0 00-3 0z" fill="currentColor" /></svg>
      )}
    </button>
  );
}
