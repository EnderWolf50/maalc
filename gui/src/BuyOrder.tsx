// The purchase order dialog of the gift list tab (#296, spec 04 section 13): one collapsible section per keyword, in buy order,
// each listing the gifts the list wants and the shop sells. Drag a keyword or a gift, or use its ▲▼, to change the order.
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { useDragSort } from "./dragSort";
import { GIFT_BY_ID, giftName, iconUrl } from "./giftCatalog";
import { buyList, moveGift, moveKeyword, nudgeGift, useGiftEdit } from "./giftEdit";
import { mainKeyword, queue } from "./gifts";
import { fill } from "./i18n";
import { KEYWORD_COLOR, TIERS, kwText } from "./KeywordGrid";
import { useEditor } from "./ui";

type Dir = "up" | "down";

/** The ▲ and ▼ of one row; `id` tells them apart ("kw:Burn", "g:9001"), `last` is the row's index when it is the last. */
function Arrows({ id, labels, at, last, onMove }: { id: string; labels: [string, string]; at: number; last: number; onMove: (dir: Dir) => void }) {
  return (["up", "down"] as const).map((dir, j) => (
    <button type="button" key={dir} className="gl-mini gl-mv" data-mv={`${id}:${dir}`} aria-label={labels[j]}
      disabled={j ? at === last : at === 0} onClick={() => onMove(dir)}>{j ? "▼" : "▲"}</button>
  ));
}

export function BuyOrderDialog({ onClose }: { onClose: () => void }) {
  const { s, t } = useEditor();
  const { list, editable, change } = useGiftEdit();
  const zh = s.language === "zh_tw";
  const [open, setOpen] = useState(() => new Set(list.order.slice(0, 1))); // the first keyword to begin with
  const [notice, setNotice] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const refocus = useRef<string>(undefined); // the arrow button to focus once the move is drawn: "kw:Burn:up"
  useLayoutEffect(() => closeButton.current?.focus(), []);
  useLayoutEffect(() => {
    if (!refocus.current) return;
    const at = refocus.current.lastIndexOf(":"), id = refocus.current.slice(0, at), dir = refocus.current.slice(at + 1);
    const button = (d: string) => box.current!.querySelector<HTMLButtonElement>(`[data-mv="${id}:${d}"]`);
    // A move to the end disables the button just pressed: the other one takes the focus.
    const target = button(dir);
    (target?.disabled ? button(dir === "up" ? "down" : "up") : target)?.focus();
    refocus.current = undefined;
  });

  const run = (fn: Parameters<typeof change>[0], focus?: string) => {
    const ok = change(fn);
    setNotice(ok ? "" : t("gl.ro"));
    if (ok) refocus.current = focus;
  };
  const dragItem = useDragSort(
    (from, to, group) => run((l) => (group === "kw" ? moveKeyword(l, from, to) : moveGift(l, Number(from), Number(to)))),
    () => { const ok = editable(); setNotice(ok ? "" : t("gl.ro")); return ok; },
  );

  // Esc and the Tab loop work from the document, so they still do when the focus fell to the page (a button went disabled).
  const onKey = useRef<(e: KeyboardEvent) => void>(undefined);
  onKey.current = (e) => {
    if (e.key === "Escape") onClose();
    if (e.key !== "Tab") return;
    const focusable = [...box.current!.querySelectorAll<HTMLElement>("button:not(:disabled)")];
    const at = focusable.indexOf(document.activeElement as HTMLElement);
    if (at < 0 || (e.shiftKey ? at === 0 : at === focusable.length - 1)) { e.preventDefault(); focusable[e.shiftKey ? focusable.length - 1 : 0].focus(); }
  };
  useEffect(() => {
    const listener = (e: KeyboardEvent) => onKey.current!(e);
    document.addEventListener("keydown", listener);
    return () => document.removeEventListener("keydown", listener);
  }, []);

  const main = mainKeyword(list), all = queue(list);
  let before = 0; // gifts bought before the keyword in view: where its range in the whole buy list starts
  return (
    <div className="gl-dlgback" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="gl-dlg" role="dialog" aria-modal="true" aria-label={t("gl.buy_title")} ref={box}>
        <div className="gl-dlgtop">
          <b>{t("gl.buy_title")}</b><small>{t("gl.buy_sub")}</small>
          <button type="button" className="gl-x" ref={closeButton} aria-label={t("gl.close")} title={`${t("gl.close")} (Esc)`} onClick={onClose}>✕</button>
        </div>
        <div className="gl-dlgbody">
          <div className="gl-accbar">
            <button type="button" className="gl-mini" onClick={() => setOpen(new Set(list.order))}>{t("gl.buy_expand")}</button>
            <button type="button" className="gl-mini" onClick={() => setOpen(new Set())}>{t("gl.buy_collapse")}</button>
            <small>{t("gl.buy_numbers")}</small>
            <span className="gl-dlgnote warn" role="status">{notice}</span>
          </div>
          {list.order.map((k, i) => {
            const gifts = buyList(list, k), isOpen = open.has(k), start = before, name = t(kwText(k));
            before += gifts.length;
            return (
              <section key={k} className="gl-agrp">
                <div className="gl-sortrow gl-ahead" {...dragItem(k, "kw")}>
                  <span className="gl-grip" aria-hidden>⠿</span>
                  <button type="button" className="gl-dnb" aria-expanded={isOpen}
                    onClick={() => setOpen((o) => { const n = new Set(o); if (!n.delete(k)) n.add(k); return n; })}>
                    <span className="gl-chev" aria-hidden>{isOpen ? "▾" : "▸"}</span>
                    <i className="gl-dot" style={{ background: KEYWORD_COLOR[k] }} aria-hidden />
                    <b>{name}</b>
                    <small>{fill(t("gl.rank"), { n: i + 1 })}・{fill(t("gl.tier_n"), { n: gifts.length })}</small>
                    <span className="spacer" />
                    <small>{gifts.length ? `#${start + 1}–${start + gifts.length}` : "—"}</small>
                  </button>
                  {k === main && <span className="gl-tag main">{t("gl.main")}</span>}
                  <Arrows id={`kw:${k}`} labels={[fill(t("gl.kw_up"), { name }), fill(t("gl.kw_down"), { name })]} at={i} last={list.order.length - 1}
                    onMove={(dir) => run((l) => moveKeyword(l, k, list.order[i + (dir === "up" ? -1 : 1)]), `kw:${k}:${dir}`)} />
                </div>
                {isOpen && (gifts.length ? (
                  <ul className="gl-rows">
                    {gifts.map((id, j) => {
                      const g = GIFT_BY_ID.get(id)!, label = giftName(g, zh), n = all.indexOf(id) + 1;
                      return (
                        <li key={id} className="gl-sortrow gl-gr" data-gift={id} {...dragItem(String(id), k)}>
                          <span className="gl-grip" aria-hidden>⠿</span>
                          <span className="gl-ord" title={fill(t("gl.queue_pos"), { n })}>{n}</span>
                          <img className="gl-ico" src={iconUrl(id)} alt="" loading="lazy" />
                          <span className="gl-qn">{label}</span>
                          <small>{TIERS[g.tier]}</small>
                          <span className="spacer" />
                          <Arrows id={`g:${id}`} labels={[fill(t("gl.up_gift"), { name: label }), fill(t("gl.down_gift"), { name: label })]} at={j} last={gifts.length - 1}
                            onMove={(dir) => run((l) => nudgeGift(l, id, dir === "up" ? -1 : 1), `g:${id}:${dir}`)} />
                        </li>
                      );
                    })}
                  </ul>
                ) : <p className="gl-dlgnote">{t("gl.buy_none")}</p>)}
              </section>
            );
          })}
        </div>
        <p className="gl-dlgfoot">{t("gl.buy_foot")}</p>
      </div>
    </div>
  );
}
