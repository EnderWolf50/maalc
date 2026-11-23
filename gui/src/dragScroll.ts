// A drag held near the top or bottom edge of the box it scrolls in scrolls that box toward the edge, faster the nearer the
// edge; it stops when the pointer leaves the edge or the window, at a drop, and when Esc cancels the drag (the browser ends
// the drag with dragend) (#916). So a theme pack goes from the top lane to the bottom one in one drag. Chromium scrolls by
// itself only within about 20 px of a box's edge (seen in the window before this, #916), and not at all past the edge, on
// the tab bar.
//
// App mounts it once for every native HTML drag the page starts (ThemePacks.tsx's packs and threshold line, ReorderList in
// ui.tsx, dragSort.ts's lists), so no list carries a copy. It listens on the document in the capture phase, ahead of the
// lists: useDragSort stops its drag events from going up, and a bar held over a box's top edge (the theme packs' pick bar)
// passes the dragover on as any element under the pointer does.
//
// What a drag holds (`Held`): the event that started it, the box it scrolls, the pointer's height at the last dragover, the
// speed of the edge zone it was picked up in, and the part of a pixel the last frame moved short. It begins at a dragstart a
// list did not refuse, scrolls from a dragover at an edge, one step a frame, and ends at the drop or the dragend. A pack
// picked up in an edge zone (the last row, half under the edge; one under the theme packs' pick bar) does not scroll the page
// away from under the pointer: that zone waits until the pointer goes nearer its edge, or leaves it. Where it was picked up
// is the dragstart's clientY: Blink sends the dragstart with the press (mouse_event_manager.cc, `mouse_down_`).
import { useEffect } from "react";

/** How far in from a box's visible top or bottom edge, CSS px, a held drag scrolls it: a quarter of a box shorter than 320. */
export const EDGE_ZONE = 80;
/** The speed at the edge and past it (the tab bar above the page), CSS px a second. From the zone's inner end it grows as the
 * square of the depth: 40 px into the zone, a quarter of it (375); the theme packs' 1362 px in names (#916) take 0.9 s at
 * the edge. */
export const EDGE_SPEED = 1500;
/** The longest frame a step takes, ms: a frame late after a stall moves no further than this. */
const MAX_FRAME = 50;

/** The speed, CSS px a second (negative: up), of a box whose visible part runs from `top` to `bottom` (window CSS px) under a
 * drag held at height `y`. */
export function edgeSpeed(y: number, top: number, bottom: number) {
  const zone = Math.min(EDGE_ZONE, (bottom - top) / 4);
  if (zone <= 0) return 0;
  const depth = y < top + zone ? (y - top - zone) / zone : y > bottom - zone ? (y - bottom + zone) / zone : 0;
  const d = Math.max(-1, Math.min(1, depth));
  return Math.sign(d) * d * d * EDGE_SPEED;
}

const SCROLLS = new Set(["auto", "scroll", "overlay"]);

/** What a dialog drawn over the page is: a drag in it never scrolls the page behind (the gift list's purchase order). */
const DIALOG = "dialog, [role=dialog]";

/** The box a drag from `from` scrolls: the nearest around it that scrolls up and down (the page, `main`; a dialog's body),
 * else the document. Not one outside a dialog: a drag in a dialog whose body fits scrolls nothing. */
function boxOf(from: EventTarget | null): HTMLElement | null {
  const start = from instanceof Element ? from : from instanceof Node ? from.parentElement : null; // a text selection: a Text
  for (let x = start; x; x = x.parentElement) {
    if (x instanceof HTMLElement && SCROLLS.has(getComputedStyle(x).overflowY) && x.scrollHeight > x.clientHeight) return x;
    if (x.matches(DIALOG)) return null;
  }
  return document.scrollingElement instanceof HTMLElement ? document.scrollingElement : null;
}

/** The visible part of `box`, from top to bottom in window CSS px: inside its border, within the window. */
function bandOf(box: HTMLElement): [number, number] {
  if (box === document.scrollingElement) return [0, window.innerHeight];
  const top = box.getBoundingClientRect().top + box.clientTop;
  return [Math.max(0, top), Math.min(window.innerHeight, top + box.clientHeight)];
}

/** Whether `box` has room to scroll at speed `v`. */
const hasRoom = (box: HTMLElement, v: number) => (v < 0 ? box.scrollTop > 0 : box.scrollTop + box.clientHeight < box.scrollHeight - 1);

/** `pickupSpeed`: the speed of the edge zone where the drag was picked up, while the scroll waits for the pointer to go
 * nearer that edge or leave the zone; 0 when it does not wait (picked up away from the edges, or since moved so). */
type Held = { start: DragEvent; box: HTMLElement; y: number | null; pickupSpeed: number; carry: number };

/** Scroll the box a drag is held near the edge of, for every drag the page starts. Mounted once, by App. */
export function useDragScroll() {
  useEffect(() => {
    let held: Held | null = null;
    let frame = 0;
    let last = 0; // the time of the frame before, 0 when this frame starts a scroll
    const halt = () => { cancelAnimationFrame(frame); frame = 0; last = 0; };
    const end = () => { held = null; halt(); };
    const step = (now: number) => {
      frame = 0;
      const h = held;
      const v = h && h.y !== null && !h.pickupSpeed ? edgeSpeed(h.y, ...bandOf(h.box)) : 0;
      if (!h || !v || !hasRoom(h.box, v)) return halt();
      const move = (v * (last ? Math.min(now - last, MAX_FRAME) : 1000 / 60)) / 1000 + h.carry;
      last = now;
      const whole = Math.trunc(move); // a box scrolls by whole pixels: a fraction would be lost on every slow frame
      h.carry = move - whole;
      h.box.scrollTop += whole;
      frame = requestAnimationFrame(step);
    };
    const on: Record<string, (e: DragEvent) => void> = {
      dragstart: (e) => {
        end();
        const box = boxOf(e.target);
        if (!box) return;
        const pickupSpeed = Number.isFinite(e.clientY) ? edgeSpeed(e.clientY, ...bandOf(box)) : 0;
        held = { start: e, box, y: null, pickupSpeed, carry: 0 };
      },
      dragover: (e) => {
        if (!held) return;
        if (held.start.defaultPrevented) return end(); // a list refused the drag (useDragSort's canDrag): none is under way
        held.y = e.clientY;
        const v = edgeSpeed(e.clientY, ...bandOf(held.box));
        const { pickupSpeed } = held;
        const stillThere = Math.sign(v) === Math.sign(pickupSpeed) && Math.abs(v) <= Math.abs(pickupSpeed);
        if (pickupSpeed && !stillThere) held.pickupSpeed = 0; // nearer the edge, or out of its zone
        if (!frame) frame = requestAnimationFrame(step);
      },
      // Blink names the element a drag enters as relatedTarget, and none when the drag leaves the page (event_handler.cc,
      // UpdateDragAndDrop and CancelDragAndDrop): out of the window, still until the next dragover
      dragleave: (e) => { if (held && e.relatedTarget === null) { held.y = null; halt(); } },
      drop: end,
      dragend: end,
    };
    for (const [type, f] of Object.entries(on)) document.addEventListener(type, f as EventListener, true);
    return () => {
      for (const [type, f] of Object.entries(on)) document.removeEventListener(type, f as EventListener, true);
      end();
    };
  }, []);
}
