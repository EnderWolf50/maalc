// The hover popover of a gift tile (#291 GUI, #307): the gift's name, a "set to" row and what the list and the recipes make of it.
// One popover for the whole tab: a tile shows it for itself (GiftEdit.tip), the tab renders it.
import { useEffect, useLayoutEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { FUSION_BY_ID, GIFT_BY_ID, giftName, iconUrl, materialsOf, packName, usedIn } from "./giftCatalog";
import { STATES, useGiftEdit, type GiftTip } from "./giftEdit";
import { lockers, queue } from "./gifts";
import { fill, TEXT, type Key } from "./i18n";
import { LockIcon, look, TIERS } from "./KeywordGrid";
import { useEditor } from "./ui";

/** How long the popover stays after the pointer leaves the tile and the popover. */
export const LEAVE_MS = 160;
const OFFSET_X = 14, OFFSET_Y = 2, MARGIN = 6;
/** At most this many uses are named; the rest are a count. */
const USED_MAX = 4;

export interface Box { left: number; top: number; right: number; bottom: number }

/** Where the popover goes (its top-left corner): its left edge 14 px right of the tile's left, 2 px under the tile; when it does not
 * fit to the right it is mirrored (its right edge 14 px left of the tile's right), when it does not fit below it goes above the tile;
 * at last it is pushed into the window. */
export function place(tile: Box, size: { w: number; h: number }, view: { w: number; h: number }): { left: number; top: number } {
  let left = tile.left + OFFSET_X, top = tile.bottom + OFFSET_Y;
  if (left + size.w > view.w - MARGIN) left = tile.right - OFFSET_X - size.w;
  if (top + size.h > view.h - MARGIN) top = tile.top - OFFSET_Y - size.h;
  const clamp = (v: number, room: number) => Math.max(MARGIN, Math.min(v, room - MARGIN));
  return { left: clamp(left, view.w - size.w), top: clamp(top, view.h - size.h) };
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

export function GiftPopover({ id, anchor }: { id: number; anchor: HTMLElement }) {
  const { s, t } = useEditor();
  const { list, readOnly, apply, goto, tip } = useGiftEdit();
  const box = useRef<HTMLDivElement>(null);
  const zh = s.language === "zh_tw";
  const g = GIFT_BY_ID.get(id)!, fusion = FUSION_BY_ID.get(id);
  const name = (x: number) => giftName(GIFT_BY_ID.get(x)!, zh);
  const { shown, locked } = look(list, id);
  const by = lockers(list, id), byNames = by.map(name).join(t("gl.sep"));
  const why = locked ? fill(t("gl.tip_locked"), { by: byNames }) : readOnly ? t("gl.tip_ro") : "";
  const users = usedIn(id);
  const buy = queue(list), at = buy.indexOf(id) + 1;

  // After every render (its height changes with the content): place it against the tile.
  useLayoutEffect(() => {
    if (!anchor.isConnected) return tip.hide(); // its tile left the page (a search, another tab): no mouseleave or blur comes
    const el = box.current!, a = anchor.getBoundingClientRect();
    const { left, top } = place(a, { w: el.offsetWidth, h: el.offsetHeight }, { w: window.innerWidth, h: window.innerHeight });
    el.style.left = `${left}px`;
    el.style.top = `${top}px`;
  });

  /** A material of the recipe; locked (tinted, padlock) while the fusion is wanted. */
  const chip = (m: number) => (
    <span key={m} className={"gl-mat" + (shown === "want" ? " locked" : "")}>
      <img src={iconUrl(m)} alt="" />{name(m)}{shown === "want" && <LockIcon className="gl-lk" />}
    </span>
  );
  const rank = g.kind === "fusion" ? t(shown === "want" ? "gl.tip_fusion_want" : "gl.tip_fusion_no")
    : at ? fill(t("gl.tip_buy_rank"), { n: at, total: buy.length }) : t("gl.tip_buy_none");

  return (
    // tabIndex -1: a click on the popover's own text keeps the focus inside it. Focus going anywhere but its tile or itself closes it.
    <div ref={box} className="gl-tip" role="dialog" aria-label={name(id)} tabIndex={-1} onMouseEnter={tip.keep} onMouseLeave={tip.leave}
      onBlur={(e) => { const to = e.relatedTarget as Element | null; if (to !== anchor && !to?.closest(".gl-tip")) tip.hide(); }}>
      <div className="gl-tip-head">
        <img src={iconUrl(id)} alt="" />
        <div><b>{name(id)}</b>{zh && <small>{g.en}</small>}</div>
      </div>
      <div className="gl-tip-set">
        <span className="k">{t("gl.tip_set")}</span>
        <div className="gl-tip-seg" role="group" aria-label={t("gl.tip_set_group")}>
          {STATES.map((v) => (
            <button type="button" key={v} className={`gl-state ${v}${shown === v ? " on" : ""}`} aria-pressed={shown === v} disabled={!!why}
              onClick={() => apply(id, v)}><i aria-hidden />{t(`state.${v}`)}</button>
          ))}
        </div>
        {why && <small className="gl-tip-why">{why}</small>}
      </div>
      <div className="gl-tip-rows">
        <Row label={t("gl.tip_cat")}>
          <span>{fill(t("gl.tip_cat_line"), { kw: t(`kw.${g.keyword}` as Key), tier: TIERS[g.tier] })}{g.kind === "fusion" && t("gl.tip_cat_fusion")}</span>
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
                    {specific && <small>{fill(t("gl.tip_pack"), { packs: packs!.map(packName).join(t("gl.sep")) })}</small>}
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
    </div>
  );
}
