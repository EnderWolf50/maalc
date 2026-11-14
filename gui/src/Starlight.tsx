// Starlight (spec 04 section 7): the game's Grace of the Star page, which the plans tab and a team's own values both edit, and
// a plan's picks on one line for a team that uses it.
import { Fragment, useId } from "react";
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
  return (
    <>{onChange && <p className="muted">{t("starlight.hint")}</p>}
    <div className={"starlight" + (onChange ? "" : " readonly")} data-path={path}>
      <div className={"graces" + (bad(`${path}/levels`) || bad(`${path}/priority`) ? " bad" : "")}>
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
                  aria-describedby={[rank > 0 && `${id}-rank-${n}`, `${id}-price-${n}`, zh && `${id}-fx-${n}`].filter(Boolean).join(" ")}>
                  <span className="title">{localName(g, zh)}{plusOf(level)}</span>
                </button>
              </div>
              {zh && g.zh && <small className="en">{g.en}</small>}
              {zh && (
                <ul id={`${id}-fx-${n}`}>
                  {effectLines(g, level).map((line, j) => (
                    <li key={j} className={line.sub ? "sub" : undefined}>
                      {line.runs.map((r, k) => (r.up ? <mark key={k}>{r.text}</mark> : <Fragment key={k}>{r.text}</Fragment>))}
                    </li>
                  ))}
                </ul>
              )}
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
