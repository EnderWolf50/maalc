// Starlight (spec 04 section 7): the game's Grace of the Star page, which the plans tab and a team's own values both edit, and
// a plan's picks on one line for a team that uses it.
import { Fragment, useEffect, useId, useLayoutEffect, useRef } from "react";
import {
  GRACES, LEVELS, allEnhanced, allSelected, buyOrder, clickCard, clickEnhance, defaultStarlight, enhanceAll, gracePrice, selectAll,
  starlightCost,
  type StarlightPlan, type StarlightValues,
} from "./model";
import { effectLines } from "./graceText";
import { localName } from "./i18n";
import { PlanTab } from "./Plans";
import { Input, Mark, useEditor } from "./ui";
import { webpFolder } from "./webpFolder";

/** The game's "Grace of the Star" page: click a card to select it at base, + / ++ to enhance it
 * (spec 04 section 7). The number on a selected card is its place in the buying order. Read-only without onChange. */
export function StarlightEditor({ value, onChange, path }: {
  value: StarlightValues; onChange?: (v: StarlightValues) => void; path: string;
}) {
  const { t, tv, bad, zh } = useEditor();
  const order = buyOrder(value);
  const set = (fn: (v: StarlightValues) => StarlightValues) => onChange?.(fn(value));
  const id = useId(); // the cards' rank, price and effects describe their pick buttons
  const graces = useFitTitles(value.levels, zh);
  return (
    <>{onChange && <p className="muted">{t("starlight.hint")}</p>}
    {/* the page's language, so the stylesheet sets an English title in the display face */}
    <div className={"starlight" + (onChange ? "" : " readonly")} data-path={path} lang={zh ? "zh-Hant" : "en"}>
      <div ref={graces} className={"graces" + (bad(`${path}/levels`) || bad(`${path}/priority`) ? " bad" : "")}>
        {GRACES.map((g, i) => {
          const n = i + 1;
          const level = value.levels[i];
          const rank = order.indexOf(n) + 1;
          return (
            // A group, not a button around buttons: its name is a pick button beside + and ++. A click anywhere on the card
            // picks it, as in the game; from the keyboard the pick button does, its click reaching the card.
            <div key={g.en} className={`grace ${level}`} role="group" aria-label={localName(g, zh)}
              aria-disabled={!onChange} title={`${n}. ${g.en} (${tv("level", level)})`}
              onClick={() => set((v) => clickCard(v, n))}>
              {rank > 0 && <span className="rank" id={`${id}-rank-${n}`}>{rank}</span>}
              <span className="price" id={`${id}-price-${n}`}><Star /> {gracePrice(n, level === "none" ? "base" : level)}</span>
              <div className="head">
                <img className="icon" src={graceIconUrl(n)} alt="" />
                <button type="button" className="name" disabled={!onChange} aria-pressed={rank > 0}
                  aria-describedby={[rank > 0 && `${id}-rank-${n}`, `${id}-price-${n}`, `${id}-fx-${n}`].filter(Boolean).join(" ")}>
                  <span className="title">{localName(g, zh)}{plusOf(level)}</span>
                </button>
              </div>
              {zh && g.zh && <small className="en">{g.en}</small>}
              <ul id={`${id}-fx-${n}`}>
                {effectLines(g, level, zh).map((line, j) => (
                  <li key={j} className={line.sub ? "sub" : undefined}>
                    {line.runs.map((r, k) => (r.up ? <mark key={k}>{r.text}</mark> : <Fragment key={k}>{r.text}</Fragment>))}
                  </li>
                ))}
              </ul>
              <span className="enhance">
                {([1, 2] as const).map((plus) => (
                  <button type="button" key={plus} disabled={!onChange} aria-pressed={level === LEVELS[plus + 1]}
                    aria-label={`${localName(g, zh)} ${"+".repeat(plus)}`}
                    onClick={(e) => { e.stopPropagation(); set((v) => clickEnhance(v, n, plus)); }}><Glyphs n={plus} /></button>
                ))}
              </span>
            </div>
          );
        })}
      </div>
      <div className="grace-side">
        {onChange && <>
          {/* lit while a second click would undo them: every card selected, every card at + or at ++ */}
          <button type="button" aria-pressed={allSelected(value)} onClick={() => set(selectAll)}>{t("starlight.selectAll")}</button>
          <span className="muted">{t("starlight.enhanceAll")}</span>
          {([1, 2] as const).map((plus) => (
            <button type="button" key={plus} className="boost" aria-label={`${t("starlight.enhanceAll")} ${"+".repeat(plus)}`}
              aria-pressed={allEnhanced(value, plus)} onClick={() => set((v) => enhanceAll(v, plus))}>
              <Glyphs n={plus} />
            </button>
          ))}
        </>}
        <span className="total">{t("starlight.total")} <b><Star /> {starlightCost(value.levels)}</b></span>
        <Mark as="label" className="check" path={`${path}/convert_leftover`}>
          <Input type="checkbox" checked={value.convert_leftover} disabled={!onChange}
            onChange={(e) => set((v) => ({ ...v, convert_leftover: e.target.checked }))} />
          {t("starlight.convert_leftover")}
        </Mark>
      </div>
    </div></>
  );
}

/** The smallest size, in px, a card's title shrinks to before it wraps: the card's smallest type, its English subtitle
 * (index.css `.grace small.en`). No
 * title gets there at the widths the cards take (#751): the longest, "Cumulating Starcloud++", takes 13 px on the narrowest (216 px). */
export const TITLE_FLOOR = 12;

/** The size, in px, that fits a title `width` px wide at the stylesheet's size `size` into its `band` px, a pixel to spare
 * (a size rounded the other way would wrap it), rounded down to a tenth and not below TITLE_FLOOR; null when it fits as it is. */
export function fittedSize(size: number, width: number, band: number): number | null {
  if (width <= band) return null;
  return Math.max(TITLE_FLOOR, Math.floor((size * (band - 1)) / width * 10) / 10);
}

/** Each card's title on one line, as the game's (#751): a title wider than its band gets the size that fits it (--fit, which
 * the stylesheet takes over its own), measured on one line. Again when a title changes (a level, the language), the cards'
 * width changes, or the display face loads after the first fit. The ref goes on the cards' grid. */
function useFitTitles(levels: string[], zh: boolean) {
  const grid = useRef<HTMLDivElement>(null);
  const fit = () => {
    for (const title of grid.current?.querySelectorAll<HTMLElement>(".grace .title") ?? []) {
      title.style.removeProperty("--fit");
      title.style.whiteSpace = "nowrap";
      const width = title.getBoundingClientRect().width;
      title.style.whiteSpace = "";
      const size = fittedSize(parseFloat(getComputedStyle(title).fontSize), width, title.parentElement!.clientWidth);
      if (size !== null) title.style.setProperty("--fit", `${size}px`);
    }
  };
  useLayoutEffect(fit, [levels, zh]);
  useEffect(() => {
    const el = grid.current;
    if (!el || typeof ResizeObserver === "undefined") return; // jsdom has none, and no layout to fit
    // the grid's width: in the next frame, so the size a fit changes is not measured inside the observer's own callback
    let frame = 0, width = 0, live = true;
    const watch = new ResizeObserver(([e]) => {
      if (e.contentRect.width === width) return; // a fit made a card taller or shorter, not narrower
      width = e.contentRect.width;
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(fit);
    });
    watch.observe(el);
    document.fonts?.ready.then(() => { if (live) fit(); });
    return () => { live = false; watch.disconnect(); cancelAnimationFrame(frame); };
  }, []);
  return grid;
}

/** The game's icon of grace n (1-10): ./grace_icons/<n>.webp (tools/grace_icons.py). */
const graceIconUrl = webpFolder(import.meta.glob<string>("./grace_icons/*.webp", { eager: true, query: "?url", import: "default" }));
/** A "★" the stylesheet covers with the game's starlight icon (gui/src/grace_card/star.webp): a screen reader and a copy keep it. */
const Star = () => <span className="star">★</span>;
/** The game's + glyph n times, for a + or ++ button; the button's aria-label names it. */
const Glyphs = ({ n }: { n: number }) => <>{Array.from({ length: n }, (_, k) => <span key={k} className="glyph" />)}</>;
/** What the game adds to a grace's title at a level: "+" at +, "++" at ++, nothing below. */
const plusOf = (level: string) => "+".repeat(Math.max(0, LEVELS.indexOf(level) - 1));

/** A starlight plan on one line, for a team that uses it: the picks in buying order with their level, and the total. */
export function StarlightReceipt({ value }: { value: StarlightValues }) {
  const { t, zh } = useEditor();
  const order = buyOrder(value);
  return (
    <div className="receipt">
      {order.length ? (
        <ol>
          {order.map((n, i) => {
            const g = GRACES[n - 1], level = value.levels[n - 1];
            return <li key={n}><b>{i + 1}</b>{localName(g, zh)}{level !== "base" && <i>{plusOf(level)}</i>}</li>;
          })}
        </ol>
      ) : <span className="muted">{t("starlight.none")}</span>}
      <span className="total">{t("starlight.total")} <b>★ {starlightCost(value.levels)}</b></span>
    </div>
  );
}

export const StarlightTab = () => (
  <PlanTab<StarlightPlan> planKey="starlight_plans" tab="tab.starlight" make={defaultStarlight}
    editor={(p, change, path) => (
      <StarlightEditor value={p} path={path} onChange={(v) => change({ ...p, ...v })} />
    )} />
);
