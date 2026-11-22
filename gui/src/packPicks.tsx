// Several theme packs picked at once (#743), for the plan editor's lanes (ThemePacks.tsx): Ctrl or Shift with a click, Space on
// a focused pack, or a box drawn from empty space in the lanes picks packs, and a drag, an Alt+arrow move or a weight typed on
// any picked pack then takes every pick (`carried`). A pick is a pack as the lanes show it: one a search or a filter hides is
// no longer picked, and another plan starts with none. What this reads of the lanes' page: each pack's element, `data-pk`
// (its name), inside its `.lane`; and `.pk` and `.thr` (OWN_PRESS) where a box may not start. Not how a lane groups its packs
// (#742): a Shift click's range and a box go by the order and the place the packs show in.
import { useEffect, useLayoutEffect, useRef, useState, type PointerEvent, type RefObject } from "react";
import { fill } from "./i18n";
import { typingIn, useEditor, useScopedState } from "./ui";

/** What a press in the lanes already starts, so a box never starts there: a pack's own click or drag, the threshold line's drag,
 * a button or a field. */
const OWN_PRESS = ".pk, .thr, button, input, select, textarea, a";
/** How far a press on empty space moves (CSS px) before it draws a box; a press that moves less is a click. */
const BOX_AFTER = 4;

type Point = { x: number; y: number };
/** A box drawn from where the press began to where the pointer is, in the lanes' own pixels: from the top left corner inside
 * their border, where an absolute child is placed. */
type Marquee = { from: Point; to: Point };

const packEls = (within: Element) => [...within.querySelectorAll<HTMLElement>("[data-pk]")];
const pointIn = (lanes: HTMLElement, x: number, y: number): Point => {
  const r = lanes.getBoundingClientRect();
  return { x: x - r.left - lanes.clientLeft, y: y - r.top - lanes.clientTop };
};

/** The packs `m` touches: each pack element whose border box overlaps it. */
function packsIn(lanes: HTMLElement, m: Marquee) {
  const [left, right] = [Math.min(m.from.x, m.to.x), Math.max(m.from.x, m.to.x)];
  const [top, bottom] = [Math.min(m.from.y, m.to.y), Math.max(m.from.y, m.to.y)];
  return packEls(lanes).filter((el) => {
    const r = el.getBoundingClientRect();
    const a = pointIn(lanes, r.left, r.top), b = pointIn(lanes, r.right, r.bottom);
    return b.x > left && a.x < right && b.y > top && a.y < bottom;
  }).map((el) => el.dataset.pk!);
}

/** The picks of the lanes in `lanes`, for the plan `scope` names, among the packs `onScreen` (the unlisted packs' chip with
 * them while it shows). */
export function usePackPicks(lanes: RefObject<HTMLElement | null>, scope: string, onScreen: ReadonlySet<string>) {
  const { t } = useEditor();
  const [held, setHeld] = useScopedState<string[]>(scope, []);
  const picks = held.filter((n) => onScreen.has(n));
  if (picks.length !== held.length) setHeld(picks); // a filter hid some: they are dropped, not kept out of sight
  // The pack last clicked, picked or unpicked by itself, in this plan: where a Shift click's range starts.
  const anchor = useRef<{ scope: string; name: string } | null>(null);
  const anchorAt = (name: string) => { anchor.current = { scope, name }; };
  // Read out by aria-live, the words anew each time, as useKeyMoves (ui.tsx) does for a list row.
  const [said, setSaid] = useState({ words: "", n: 0 });
  const say = (words: string) => setSaid((x) => ({ words, n: x.n + 1 }));
  const sayPicked = (n: number) => say(n ? fill(t("packs.picked"), { n }) : t("packs.unpicked"));
  const pick = (next: string[]) => { setHeld(next); sayPicked(next.length); };
  const clear = () => { if (picks.length) pick([]); };
  const toggle = (name: string) => {
    anchorAt(name);
    pick(picks.includes(name) ? picks.filter((n) => n !== name) : [...picks, name]);
  };

  // Esc drops the picks from anywhere on the page but a field, whose own Esc closes a weight box or clears the search.
  useEffect(() => {
    if (!picks.length) return;
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape" && !e.defaultPrevented && !typingIn(e.target)) pick([]); };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  });

  // A pack moved from the keyboard leaves its lane for another, a new element there: the focus goes back to it once it shows.
  const follow = useRef<string | null>(null);
  useLayoutEffect(() => {
    if (follow.current === null || !lanes.current) return;
    const name = follow.current;
    follow.current = null;
    packEls(lanes.current).find((el) => el.dataset.pk === name)?.focus();
  });

  const [drawn, setDrawn] = useState<Marquee | null>(null);
  const press = useRef<{ from: Point; base: string[]; drawn: boolean } | null>(null);
  const end = (e: PointerEvent<HTMLElement>, done: boolean) => {
    const p = press.current;
    press.current = null;
    if (!p) return;
    setDrawn(null);
    if (!done) return;
    if (p.drawn) sayPicked(picks.length);
    else if (!e.ctrlKey) clear(); // a click on empty space: a box that touched nothing
  };

  return {
    picks,
    has: (name: string) => picks.includes(name),
    /** What a drag or a move of `name` takes: every pick when it is one of several, else itself alone. */
    carried: (name: string) => (picks.length > 1 && picks.includes(name) ? picks : [name]),
    toggle,
    clear,
    /** A plain click on `name`: a Shift click's range starts there next. */
    anchorAt,
    /** A Shift click: the range of `name`'s lane, in the order it shows, from the pack last clicked, picked or unpicked by
     * itself to `name`, added to the picks. With no such pack in that lane, `name` alone is picked or unpicked. */
    extend(name: string) {
      const lane = lanes.current && packEls(lanes.current).find((el) => el.dataset.pk === name)?.closest(".lane");
      const names = lane ? packEls(lane).map((el) => el.dataset.pk!) : [];
      const a = anchor.current?.scope === scope ? anchor.current.name : null;
      if (a === null || !names.includes(a)) { toggle(name); return; }
      const [i, j] = [names.indexOf(a), names.indexOf(name)].sort((x, y) => x - y);
      pick([...new Set([...picks, ...names.slice(i, j + 1)])]);
    },
    say,
    /** Give the focus back to `name` after the render that moves it. */
    follow: (name: string) => { follow.current = name; },
    /** Spread on the lanes' element: a press on empty space draws a box, which picks every pack it touches; with Ctrl they
     * are added to the picks, without it they replace them. */
    onLanes: {
      onPointerDown(e: PointerEvent<HTMLElement>) {
        if (e.button !== 0 || !(e.target instanceof Element) || e.target.closest(OWN_PRESS)) return;
        press.current = { from: pointIn(e.currentTarget, e.clientX, e.clientY), base: e.ctrlKey ? picks : [], drawn: false };
        e.currentTarget.setPointerCapture?.(e.pointerId); // the box follows the pointer out of the lanes (jsdom has no capture)
      },
      onPointerMove(e: PointerEvent<HTMLElement>) {
        const p = press.current;
        if (!p) return;
        const to = pointIn(e.currentTarget, e.clientX, e.clientY);
        if (!p.drawn && Math.hypot(to.x - p.from.x, to.y - p.from.y) < BOX_AFTER) return;
        if (!p.drawn) window.getSelection()?.removeAllRanges(); // the press began a text selection: a box selects no text
        p.drawn = true;
        const m = { from: p.from, to };
        setDrawn(m);
        setHeld([...new Set([...p.base, ...packsIn(e.currentTarget, m)])]);
      },
      onPointerUp: (e: PointerEvent<HTMLElement>) => end(e, true),
      onPointerCancel: (e: PointerEvent<HTMLElement>) => end(e, false),
    },
    drawing: drawn !== null,
    marquee: drawn && (
      <div className="marquee" aria-hidden style={{
        left: Math.min(drawn.from.x, drawn.to.x), top: Math.min(drawn.from.y, drawn.to.y),
        width: Math.abs(drawn.to.x - drawn.from.x), height: Math.abs(drawn.to.y - drawn.from.y),
      }} />
    ),
    readOut: <span className="sr-only" aria-live="polite">{said.words && <span key={said.n}>{said.words}</span>}</span>,
  };
}
