// The gift list tab's keyword tabs and the grid of one keyword: tier blocks of icon tiles, one tile per gift.
import { useRef, useState, type KeyboardEvent } from "react";
import { CATALOG, GIFT_BY_ID, giftName, iconUrl, keywordIconUrl, tiersOf } from "./giftCatalog";
import { useDragSort, type DragProps } from "./dragSort";
import { moveGift, useGiftEdit } from "./giftEdit";
import { effective, mainKeyword, state, type GiftState, type ListRules } from "./gifts";
import { fill, type Key } from "./i18n";
import { GIFT_KEYWORDS } from "./model";
import { useEditor } from "./ui";

export const TIERS = ["", "I", "II", "III", "IV", "V"];
/** A keyword's game icon; Keywordless has none and gets a neutral dot. */
export function KeywordIcon({ keyword, big }: { keyword: string; big?: boolean }) {
  const src = keywordIconUrl(keyword);
  return src ? <img className={"gl-kwi" + (big ? " big" : "")} src={src} alt="" /> : <i className={"gl-dot" + (big ? " big" : "")} aria-hidden />;
}
export const kwText = (k: string) => `kw.${k}` as Key;

/** What the list makes of a gift for display: its effective state, and whether a wanted fusion locks it (shown kept). */
export function look(list: ListRules, id: number): { shown: GiftState; locked: boolean } {
  const shown = effective(list, id);
  return { shown, locked: shown === "keep" && state(list, id) === "drop" };
}

/** What a keyword has set in the list itself: wanted and kept gifts, wanted fusion gifts (a locked material is not set). */
function counts(list: ListRules, keyword: string) {
  const c = { want: 0, keep: 0, fusion: 0 };
  for (const { ids } of tiersOf(list.gorder, keyword)) {
    for (const id of ids) {
      const set = state(list, id);
      if (set === "drop") continue;
      if (set === "want" && GIFT_BY_ID.get(id)!.kind === "fusion") c.fusion++;
      else c[set]++;
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
    const next = tab ? GIFT_KEYWORDS[GIFT_KEYWORDS.indexOf(tab) + step] : GIFT_KEYWORDS[0]; // no tab chosen (searching): the first
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
          <button type="button" key={k} id={`gl-tab-${k}`} role="tab" aria-selected={on} aria-controls="gl-panel" tabIndex={on || (!tab && k === GIFT_KEYWORDS[0]) ? 0 : -1}
            className={"gl-tab" + (on ? " on" : "")} ref={(el) => { refs.current[k] = el; }} onClick={() => onTab(k)}>
            <KeywordIcon keyword={k} />
            <span>{t(kwText(k))}</span>
            {n > 0 && <b className="gl-n" title={fill(t("gl.tier_set"), { n })}>{n}</b>}
          </button>
        );
      })}
    </div>
  );
}

/** Roving tabindex and arrow-key walking over the tiles of one grid: one tile is the tab stop (the one that last had focus if
 * `owns` it, else `first`); the arrow keys move between tiles. */
function useTileGrid(owns: (id: number) => boolean, first: number | undefined) {
  const grid = useRef<HTMLDivElement>(null);
  const [focused, setFocused] = useState<number | null>(null);
  const stop = focused !== null && owns(focused) ? focused : first;

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
  return { grid, stop, walk, onFocus: setFocused };
}

/** One keyword's header and its tier blocks. */
export function KeywordPanel({ keyword }: { keyword: string }) {
  const { s, t } = useEditor();
  const { list, change, editable } = useGiftEdit();
  const dragItem = useDragSort((from, to) => change((l) => moveGift(l, Number(from), Number(to))), editable);
  const zh = s.language === "zh_tw";
  const c = counts(list, keyword), blocks = tiersOf(list.gorder, keyword);
  const { grid, stop, walk, onFocus } = useTileGrid((id) => GIFT_BY_ID.get(id)?.keyword === keyword, blocks[0]?.ids[0]);

  return (
    <div ref={grid} onKeyDown={walk}>
      <h3 className="gl-kwh">
        <KeywordIcon keyword={keyword} big />
        <b>{t(kwText(keyword))}</b>{zh && keyword !== "Keywordless" && <small>{keyword}</small>}
        {keyword === mainKeyword(list) && <span className="gl-tag main">{t("gl.main")}</span>}
        <span className="gl-tag">{fill(t("gl.rank"), { n: list.order.indexOf(keyword) + 1 })}</span>
        {c.want > 0 && <span className="gl-tag want">{fill(t("gl.n_want"), { n: c.want })}</span>}
        {c.keep > 0 && <span className="gl-tag keep">{fill(t("gl.n_keep"), { n: c.keep })}</span>}
        {c.fusion > 0 && <span className="gl-tag fusion">{fill(t("gl.n_fusion"), { n: c.fusion })}</span>}
      </h3>
      {blocks.map(({ tier, ids }) => {
        const kinds = ids.map((id) => GIFT_BY_ID.get(id)!.kind);
        const set = ids.filter((id) => state(list, id) !== "drop").length;
        const note = kinds.includes("fusion") ? t("gl.tier_fusion") : kinds.some((k) => k === "material" || k === "vestige") ? t("gl.tier_unbuyable") : "";
        return (
          <section key={tier} className="gl-tier" aria-label={TIERS[tier]}>
            <h4><span className={"gl-tierno" + (tier >= 4 ? " fusion" : "")}>{TIERS[tier]}</span>
              <small>{note && `${note}・`}{fill(t("gl.tier_n"), { n: ids.length })}{set > 0 && `・${fill(t("gl.tier_set"), { n: set })}`}</small></h4>
            <div className="gl-wall">
              {/* A gift the shop sells can be dragged onto another of its tier to change its place in the buy order. */}
              {ids.map((id) => (
                <GiftTile key={id} id={id} zh={zh} tabStop={id === stop} onFocus={() => onFocus(id)}
                  drag={GIFT_BY_ID.get(id)!.kind === "buyable" ? dragItem(String(id), `${keyword}:${tier}`) : undefined} />
              ))}
            </div>
          </section>
        );
      })}
    </div>
  );
}

/** The gifts whose Chinese name, English name or id (all of it) match what was typed, grouped by keyword in the list's order. */
export function SearchResults({ query, onClear }: { query: string; onClear: () => void }) {
  const { s, t } = useEditor();
  const { list } = useGiftEdit();
  const zh = s.language === "zh_tw", q = query.trim().toLowerCase();
  const hit = new Set(CATALOG.filter((g) => g.zh.toLowerCase().includes(q) || g.en.toLowerCase().includes(q) || String(g.id) === q).map((g) => g.id));
  const groups = list.order
    .map((keyword) => ({ keyword, ids: tiersOf(list.gorder, keyword).flatMap((b) => b.ids).filter((id) => hit.has(id)) }))
    .filter((grp) => grp.ids.length);
  const total = groups.reduce((n, grp) => n + grp.ids.length, 0);
  const { grid, stop, walk, onFocus } = useTileGrid((id) => hit.has(id), groups[0]?.ids[0]);
  if (!total) {
    return (
      <div className="gl-empty">
        <b>{fill(t("gl.search_none"), { q: query })}</b>
        <p>{t("gl.search_none_note")}</p>
        <button type="button" onClick={onClear}>{t("gl.search_clear")}</button>
      </div>
    );
  }
  return (
    <div ref={grid} onKeyDown={walk}>
      <div className="gl-sh"><b>{fill(t("gl.search_n"), { n: total })}</b><button type="button" onClick={onClear}>{t("gl.search_clear")}</button></div>
      {groups.map(({ keyword, ids }) => (
        <section key={keyword} className="gl-tier" aria-label={t(kwText(keyword))}>
          <h3 className="gl-kwh"><KeywordIcon keyword={keyword} /><b>{t(kwText(keyword))}</b></h3>
          <div className="gl-wall">{ids.map((id) => <GiftTile key={id} id={id} zh={zh} tabStop={id === stop} onFocus={() => onFocus(id)} />)}</div>
        </section>
      ))}
    </div>
  );
}

/** The padlock of a gift locked by a wanted fusion (on its tile, and in the popover). */
export const LockIcon = ({ className }: { className: string }) => (
  <svg className={className} viewBox="0 0 16 16" aria-hidden><path d="M5 7V5a3 3 0 016 0v2h1v7H4V7zm1.5 0h3V5a1.5 1.5 0 00-3 0z" fill="currentColor" /></svg>
);

/** One gift: its icon in a frame that shows its state (want thick and striped, keep solid, drop faded, locked dashed with a padlock). */
function GiftTile({ id, zh, tabStop, onFocus, drag }: {
  id: number; zh: boolean; tabStop: boolean; onFocus: () => void; drag?: DragProps;
}) {
  const { t } = useEditor();
  const { list, apply, tip } = useGiftEdit();
  const g = GIFT_BY_ID.get(id)!;
  const { shown, locked } = look(list, id);
  const label = fill(t("gl.tile"), { name: giftName(g, zh), tier: TIERS[g.tier], state: t(`state.${shown}`), lock: locked ? t("gl.locked") : "" });
  return (
    <button type="button" className={`gl-tile ${shown}${locked ? " locked" : ""}`} aria-label={label} data-gift={id} tabIndex={tabStop ? 0 : -1}
      draggable={false} {...drag}
      onDragStart={(e) => { tip.hide(); drag?.onDragStart(e); }}
      onFocus={(e) => { onFocus(); tip.show(id, e.currentTarget); }}
      onBlur={(e) => { if (!(e.relatedTarget as Element | null)?.closest(".gl-tip")) tip.hide(); }}
      onMouseEnter={(e) => tip.show(id, e.currentTarget)} onMouseLeave={tip.leave} onClick={() => apply(id)}>
      <img src={iconUrl(id)} alt="" loading="lazy" />
      {locked && <LockIcon className="gl-lock" />}
    </button>
  );
}
