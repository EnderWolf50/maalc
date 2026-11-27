// The hover card of a gift tile (#291 GUI, #307): the gift's icon and name, its effect as the game's gift panel prints it (#721,
// #764), and under them what the page has to say about it. The gift list tab's says "set to" and what the list and the recipes
// make of it; the team page's Gift Search says why a gift cannot be picked. One card for a page: a tile shows it for itself (a
// GiftTip), the page renders it.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { bufIconUrl, FUSION_BY_ID, GIFT_BY_ID, giftEffect, giftLevels, giftSin, iconUrl, keywordIconUrl, packName, packsOf, plateOf, STATUS_WORDS, usedIn, type Colour, type EffectRun, type Level } from "./giftCatalog";
import { plan, STATES, useGiftEdit, type GiftTip } from "./giftEdit";
import { lockers, materialsOf, purchases, queue, type GiftState } from "./gifts";
import { fill, localName, TEXT, type Key } from "./i18n";
import { LockIcon, look, TIERS } from "./KeywordGrid";
import { useEditor } from "./ui";

/** How long the popover stays after the pointer leaves the tile and the popover. */
export const LEAVE_MS = 160;
/** The popover's left edge from the tile's; its gap to the tile, under, over or beside it; its least distance to the window's edge. */
const OFFSET_X = 14, GAP = 2, MARGIN = 6;
/** At most this many uses are named; the rest are a count. */
const USED_MAX = 4;

export interface Box { left: number; top: number; right: number; bottom: number }

/** Where the popover goes (its top-left corner), never over its tile (#721): its left edge 14 px right of the tile's left, 2 px
 * under the tile; when it does not fit to the right it is mirrored (its right edge 14 px left of the tile's right), when it does not
 * fit below it goes above the tile. When it fits neither below nor above (a tall popover in a short window) it goes beside the tile,
 * 2 px off its right edge (its left edge when there is no room to the right), level with the tile's top. When it fits on no side (a
 * wide tile mid-window) it goes under or over the tile, whichever has more room, and `maxHeight` cuts it to that room (it scrolls).
 * At last it is pushed into the window. */
export function place(tile: Box, size: { w: number; h: number }, view: { w: number; h: number }): { left: number; top: number; maxHeight?: number } {
  const fitsX = (left: number) => left >= MARGIN && left + size.w <= view.w - MARGIN;
  const clamp = (v: number, room: number) => Math.max(MARGIN, Math.min(v, room - MARGIN));
  let left = tile.left + OFFSET_X;
  if (!fitsX(left)) left = tile.right - OFFSET_X - size.w;
  const under = view.h - MARGIN - (tile.bottom + GAP), over = tile.top - GAP - MARGIN; // the room under and over the tile
  if (size.h <= under) return { left: clamp(left, view.w - size.w), top: tile.bottom + GAP };
  if (size.h <= over) return { left: clamp(left, view.w - size.w), top: tile.top - GAP - size.h };
  const beside = [tile.right + GAP, tile.left - GAP - size.w].find(fitsX);
  if (beside !== undefined) return { left: beside, top: clamp(tile.top, view.h - size.h) };
  return under >= over
    ? { left: clamp(left, view.w - size.w), top: tile.bottom + GAP, maxHeight: under }
    : { left: clamp(left, view.w - size.w), top: MARGIN, maxHeight: over };
}

/** The popover's state for the tab: which gift it shows and the tile it hangs from, and the GiftTip the tiles use. Scrolling,
 * resizing and the window losing focus close it at once. */
export function useGiftTip(): { open: { id: number; anchor: HTMLElement } | null; tip: GiftTip } {
  const [open, setOpen] = useState<{ id: number; anchor: HTMLElement } | null>(null);
  const timer = useRef<number>(undefined);
  const tip = useMemo<GiftTip>(() => ({
    show: (id, anchor) => { clearTimeout(timer.current); setOpen({ id, anchor }); },
    keep: () => clearTimeout(timer.current),
    leave: () => { clearTimeout(timer.current); timer.current = window.setTimeout(() => setOpen(null), LEAVE_MS); },
    hide: () => { clearTimeout(timer.current); setOpen(null); },
  }), []);
  useEffect(() => () => clearTimeout(timer.current), []);
  const shown = open !== null;
  useEffect(() => {
    if (!shown) return;
    // The popover scrolls inside itself when it is tall: that is not the page moving.
    const onScroll = (e: Event) => { if (!(e.target instanceof Element && e.target.closest(".gl-tip"))) tip.hide(); };
    const close = () => tip.hide();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("blur", close);
    window.addEventListener("resize", close);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("blur", close);
      window.removeEventListener("resize", close);
    };
  }, [shown, tip]);
  return { open, tip };
}

/** "A、B 的材料", or "A、B、C、D 等 6 個的材料" when there are more than four. */
export function usedText(names: string[], text: Record<Key, string>): string {
  const sep = text["gl.sep"];
  return names.length > USED_MAX
    ? fill(text["gl.tip_used_more"], { names: names.slice(0, USED_MAX).join(sep), n: names.length })
    : fill(text["gl.tip_used_list"], { names: names.join(sep) });
}

function Row({ label, children }: { label: string; children: ReactNode }) {
  return <div className="gl-tip-row"><span className="k">{label}</span><div className="v">{children}</div></div>;
}

/** The class of a colour of the effect text: its theme's shade of the game's colour (index.css --kw-pos, --kw-neg, --kw-neu). */
const COLOUR_CLASS: Record<Colour, string> = { Positive: "gl-pos", Negative: "gl-neg", Neutral: "gl-neu" };

/** A gift's effect text as the game's gift panel prints it (#764): a status word as its status icon, then its name underlined in
 * its buff's colour; flavour text italic, in its colour when the text gives one; the rest, a bracketed note too, as written.
 * What a + or ++ changed (`up`, #961) is marked, in the game's yellow, a status word's name too. */
export function EffectText({ runs, zh }: { runs: EffectRun[]; zh: boolean }) {
  return (
    <p className="gl-tip-effect">
      {runs.map((r, i) => {
        if (typeof r === "string") return r;
        let run: ReactNode;
        if ("kw" in r) {
          const word = STATUS_WORDS[r.kw];
          run = (
            <span key={i} className="gl-kw">
              <img src={bufIconUrl(word.icon)} alt="" /><span className={"gl-kw-name " + COLOUR_CLASS[word.colour]}>{zh ? word.zh : word.en}</span>
            </span>
          );
        } else {
          const colour = r.colour ? COLOUR_CLASS[r.colour] : "";
          run = r.i ? <i key={i} className={("gl-fl " + colour).trim()}>{r.text}</i> : <span key={i} className={colour}>{r.text}</span>;
        }
        return r.up ? <mark key={i} className="gl-up">{run}</mark> : run;
      })}
    </p>
  );
}

/** The switch's label of each level, as the game writes a gift's + and ++. */
const LEVEL_GLYPHS: Record<Level, string> = { base: "−", plus: "＋", plus2: "＋＋" };

/** The card's frame: the gift's icon with its tier at the top left and the icon of its keyword (its 體系) at the bottom right,
 * as the game's panel draws it; its name on the plate of its sin (#786) and, in Chinese, its English name under the plate;
 * its effect; under it, when the gift has a + (#961), a row that switches the effect between −, ＋ and ＋＋ (the levels it has),
 * at − each time the card opens or shows another gift, the card as wide as without it (the user, 2026-11-27); then `children`
 * (on the Gift Search, why it cannot be picked). Placed against its tile (`place`) and kept open while the pointer is on it; focus going anywhere
 * but its tile or itself closes it. */
export function GiftCard({ id, anchor, tip, children }: { id: number; anchor: HTMLElement; tip: GiftTip; children?: ReactNode }) {
  const { t, zh } = useEditor();
  const box = useRef<HTMLDivElement>(null);
  // the level picked on this gift's card. Another gift starts at −, and the pick is dropped then, so that a pointer back on the
  // first gift's tile (the card never closed between) starts at − too; the card opened again is mounted anew.
  const [picked, pick] = useState<{ id: number; level: Level }>({ id, level: "base" });
  if (picked.id !== id) pick({ id, level: "base" });
  const level = picked.id === id ? picked.level : "base", levels = giftLevels(id);
  const g = GIFT_BY_ID.get(id)!, name = localName(g, zh), effect = giftEffect(id, zh, level), categoryIcon = keywordIconUrl(g.keyword);
  const plate = plateOf(giftSin(id)!);

  // After every render (its height changes with the content): place it against the tile.
  useLayoutEffect(() => {
    if (!anchor.isConnected) return tip.hide(); // its tile left the page (a search, another tab): no mouseleave or blur comes
    const el = box.current!, a = anchor.getBoundingClientRect();
    el.style.maxHeight = ""; // measured at its own height, not the cut of the last placing
    const { left, top, maxHeight } = place(a, { w: el.offsetWidth, h: el.offsetHeight }, { w: window.innerWidth, h: window.innerHeight });
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
    if (maxHeight !== undefined) el.style.maxHeight = `${maxHeight}px`;
  });

  return (
    // tabIndex -1: a click on the card's own text keeps the focus inside it.
    <div ref={box} className="gl-tip" role="dialog" aria-label={name} tabIndex={-1} onMouseEnter={tip.keep} onMouseLeave={tip.leave}
      onBlur={(e) => { const to = e.relatedTarget as Element | null; if (to !== anchor && !to?.closest(".gl-tip")) tip.hide(); }}>
      <div className="gl-tip-head">
        <span className="gl-tip-icon">
          <img src={iconUrl(id)} alt="" />
          <b className="gl-tip-tier">{TIERS[g.tier]}</b>
          {categoryIcon && <img className="gl-tip-kwi" src={categoryIcon} alt="" />}
        </span>
        <div>
          <b className="gl-plate" data-ink={plate.ink} style={{ "--plate": `url(${plate.url})`, color: plate.colour } as CSSProperties}>{name}</b>
          {zh && <small>{g.en}</small>}
        </div>
      </div>
      {effect && <EffectText runs={effect} zh={zh} />}
      {levels.length > 1 && (
        <div className="gl-tip-lv" role="group" aria-label={t("gl.tip_level_group")}>
          {levels.map((l) => (
            <button type="button" key={l} aria-pressed={l === level} aria-label={t(`gl.tip_level_${l}`)} title={t(`gl.tip_level_${l}`)}
              onClick={() => pick({ id, level: l })}>{LEVEL_GLYPHS[l]}</button>
          ))}
        </div>
      )}
      {children}
    </div>
  );
}

/** The gift list tab's card: "set to", and what the list and the recipes make of the gift. */
export function GiftPopover({ id, anchor }: { id: number; anchor: HTMLElement }) {
  const { s, t, zh } = useEditor();
  const { list, readOnly, apply, goto, tip } = useGiftEdit();
  const g = GIFT_BY_ID.get(id)!, fusion = FUSION_BY_ID.get(id);
  const name = (x: number) => localName(GIFT_BY_ID.get(x)!, zh);
  const { shown, locked } = look(list, id);
  const by = lockers(list, id), byNames = by.map(name).join(t("gl.sep"));
  const refused = (v: GiftState) => "locked" in plan(list, id, v); // as the tab's apply refuses it
  const why = locked ? fill(t(refused("want") ? "gl.tip_locked_nowant" : "gl.tip_locked"), { by: byNames }) : readOnly ? t("gl.tip_ro") : "";
  const users = usedIn(id);
  const buy = queue(list), at = buy.indexOf(id) + 1;
  const forFusion = at ? null : purchases(list).find(([i]) => i === id)?.[1]; // a wanted fusion's material, bought after the wants
  const packs = g.kind === "buyable" ? packsOf(id) : []; // the only packs a pack's own gift shows in (#626)
  const packList = (ids: number[]) => ids.map((p) => packName(p, zh)).join(t("gl.sep")); // in Chinese in the Chinese UI (#899)

  /** A material of the recipe; locked (tinted, padlock) while the fusion is wanted. */
  const chip = (m: number) => (
    <span key={m} className={"gl-mat" + (shown === "want" ? " locked" : "")}>
      <img src={iconUrl(m)} alt="" />{name(m)}{shown === "want" && <LockIcon className="gl-lk" />}
    </span>
  );
  const rank = g.kind === "fusion" ? t(shown === "want" ? "gl.tip_fusion_want" : "gl.tip_fusion_no")
    : at ? fill(t("gl.tip_buy_rank"), { n: at, total: buy.length })
    : forFusion ? fill(t("gl.tip_buy_fusion"), { name: name(forFusion) }) : t("gl.tip_buy_none");

  return (
    <GiftCard id={id} anchor={anchor} tip={tip}>
      <div className="gl-tip-set">
        <span className="k">{t("gl.tip_set")}</span>
        <div className="gl-tip-seg" role="group" aria-label={t("gl.tip_set_group")}>
          {STATES.map((v) => (
            <button type="button" key={v} className={`gl-state ${v}${shown === v ? " on" : ""}`} aria-pressed={shown === v}
              disabled={readOnly || refused(v)}
              onClick={() => apply(id, v)}><i aria-hidden />{t(`state.${v}`)}</button>
          ))}
        </div>
        {why && <small className="gl-tip-why">{why}</small>}
      </div>
      <div className="gl-tip-rows">
        <Row label={t("gl.tip_cat")}>
          <span>{fill(t("gl.tip_cat_line"), { kw: t(`kw.${g.keyword}` as Key), tier: TIERS[g.tier] })}{g.kind === "fusion" && t("gl.tip_cat_fusion")}
            {packs.length > 0 && fill(t("gl.tip_cat_pack"), { packs: packList(packs) })}</span>
        </Row>
        {locked && (
          <Row label={t("gl.tip_lock")}>
            <div>
              <span className="gl-tip-lockwhy"><LockIcon className="gl-lk" />{fill(t("gl.tip_lock_why"), { by: byNames })}</span>
              {by.map((f) => {
                const { specific, packs } = FUSION_BY_ID.get(f)!;
                return (
                  <div key={f} className="gl-tip-acts">
                    <button type="button" onClick={() => goto(f)}>{fill(t("gl.tip_goto"), { name: name(f) })}</button>
                    <button type="button" className="warn" onClick={() => apply(f, "drop")}>{t("gl.tip_unwant")}</button>
                    {specific && <small>{fill(t("gl.tip_pack"), { packs: packList(packs!) })}</small>}
                  </div>
                );
              })}
            </div>
          </Row>
        )}
        {fusion && shown === "want" && (
          <Row label={t("gl.tip_mats")}>
            <span>{fusion.groups
              ? fill(t("gl.tip_mats_mix"), { a: fusion.groups[0].ids.length, b: fusion.groups[1].ids.length, n: materialsOf(fusion).length })
              : fill(t("gl.tip_mats_all"), { n: materialsOf(fusion).length })}</span>
          </Row>
        )}
        {users.length > 0 && (
          <Row label={t("gl.tip_used")}>
            <span>{usedText(users.map((f) => name(f.id) + (f.groups ? t("gl.tip_any") : "")), TEXT[s.language])}</span>
          </Row>
        )}
        {fusion && (
          <Row label={t("gl.tip_recipe")}>
            <div className="gl-tip-recipes">
              {fusion.recipes?.map((recipe, i) => (
                <div key={i} className="gl-tip-recipe">
                  {fusion.recipes!.length > 1 && <span className="gl-tip-no">{i + 1}</span>}
                  {recipe.flatMap((m, j) => [j > 0 && <i key={`p${j}`}>＋</i>, chip(m)])}
                </div>
              ))}
              {fusion.groups?.map((grp, i) => (
                <div key={i} className="gl-tip-group">
                  {/* The only recipe with groups is Lunar Memory: its first group is fragments, its second memories. */}
                  <span className={"gl-tip-need" + (grp.need === grp.ids.length ? " all" : "")}>
                    {fill(t("gl.tip_group"), { name: t(i === 0 ? "gl.tip_fragment" : "gl.tip_memory"), n: grp.ids.length, need: grp.need })}
                    {grp.need === grp.ids.length && t("gl.tip_all")}
                  </span>
                  <div className="gl-tip-chips">{grp.ids.map(chip)}</div>
                </div>
              ))}
            </div>
          </Row>
        )}
        <Row label={t("gl.tip_rank")}><span>{rank}</span></Row>
      </div>
    </GiftCard>
  );
}
