// Theme pack plans (spec 04 section 8): lanes of weights with the refresh threshold between them, and the locked default plan
// above the user's own.
import { Fragment, useEffect, useId, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent } from "react";
import { fill, type Key } from "./i18n";
import {
  EVENT_MODES, MODE_BANDS, MODE_KEYS, THEME_PACKS, WEIGHT_MAX, WEIGHT_MIN, floorBadges, lanesOf, lineAt, newPackPlan, onFloor,
  packGroups, weightOf, type PackGroup, type PackMode, type PackPlanValues, type ThemePackPlan, type ThemePacks,
} from "./model";
import { PlanTab } from "./Plans";
import { Field, Select, useEditor, useSlashFocus, withBreaks } from "./ui";
import { webpFolder } from "./gameData";
import { usePackPicks } from "./packPicks";

export function ThemePackTab() {
  const { t } = useEditor();
  const data = THEME_PACKS;
  return (
    <PlanTab<ThemePackPlan> planKey="theme_pack_plans" tab="tab.themepacks" make={newPackPlan}
      lead={{ id: "default", label: t("defaultPlanLocked"), body: <>
        <p className="muted">{t("defaultPlanNote")}</p>
        <PackPlanEditor data={data} plan={data.default_plan} path="" />
      </> }}
      editor={(p, change, path) => <>
        <PackPlanEditor data={data} plan={p} path={path} onChange={(v) => change({ ...p, ...v })} />
      </>} />
  );
}

// #241's cards (theme_pack_covers/index.json: pack name -> file); a pack without one shows its name on a
// blank card. The title is printed on the card, so the name is the tooltip.
const coverOf = webpFolder("theme_pack_covers", "theme_pack_covers/index.json");

const UNLISTED = "\u0000unlisted"; // what the "unlisted packs" chip drags: no pack name starts with NUL
const LINE = "\u0000line";
const PICKS = "\u0000picks"; // what a weight box types for: every pick (#743)
/** The two + lanes a pack is dropped on for a new weight: above the lanes and below them (#720). */
type AddAt = "top" | "bottom";
/** The floor filter's chips (0: any): a run's 15 floors, 6-10 INFINITY's and 11-15 EXTREME's (#387). */
const FLOORS = Array.from({ length: 16 }, (_, i) => i);
/** A floor badge's label and class per mode of the data file. */
const BADGES = {
  N: ["packs.floorsNormal", ""], H: ["packs.floorsHard", " hard"], I: ["packs.floorsInfinity", " inf"], X: ["packs.floorsExtreme", " ext"],
} as const;
/** A long lane's group (#742): its title and the small note beside it ({n}: EXTREME's floors). */
const GROUPS: Record<PackGroup, { title: Key; note?: Key }> = {
  both: { title: "packs.groupBoth" },
  hard: { title: "packs.groupHard", note: "packs.groupHardNote" },
  extreme: { title: "packs.groupExtreme", note: "packs.groupExtremeNote" },
  other: { title: "packs.groupOther" },
};

/** A pack's weight typed in place (#679, in place of prompt()): Enter keeps a whole number from -10 to 10, or says why not
 * beside the box; leaving the box keeps a number typed into it as Enter does, and leaves the weight as it was when nothing
 * was typed or what was typed is no such number (#739); Esc leaves it as it was. The weight it opens on is selected, so a
 * number typed replaces it (#734). */
function WeightBox({ value, onDone }: { value?: number; onDone: (w: number | null) => void }) {
  const { t } = useEditor();
  const [text, setText] = useState(value === undefined ? "" : String(value));
  const [typed, setTyped] = useState(false);
  const [wrong, setWrong] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  const closed = useRef(false); // by Enter or Esc: a blur as the box goes keeps nothing more
  useEffect(() => { input.current?.select(); }, []);
  const score = () => {
    const w = Number(text);
    return text.trim() !== "" && Number.isInteger(w) && w >= WEIGHT_MIN && w <= WEIGHT_MAX ? w : null;
  };
  const close = (w: number | null) => { closed.current = true; onDone(w); };
  return (
    <span className="weigh">
      <input ref={input} type="number" min={WEIGHT_MIN} max={WEIGHT_MAX} step={1} autoFocus aria-label={t("packs.weightPrompt")} value={text}
        onChange={(e) => { setText(e.target.value); setTyped(true); setWrong(false); }}
        onBlur={() => { if (!closed.current) close(typed ? score() : null); }}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); const w = score(); if (w === null) setWrong(true); else close(w); }
          if (e.key === "Escape") close(null);
        }} />
      {wrong && <small>{t("packs.weightRange")}</small>}
    </span>
  );
}

/** Design A of #240: one lane per weight in use (0 always), highest first, and the threshold line between lanes.
 * Drag a pack to another lane, or onto + for a new weight; click one to type its weight. Several packs picked (#743,
 * packPicks.tsx) move as one: a drag, Alt+↑/↓ or a weight typed on any of them moves them all. Read-only without onChange. */
function PackPlanEditor({ data, plan, path, onChange }: {
  data: ThemePacks; plan: PackPlanValues; path: string; onChange?: (p: PackPlanValues) => void;
}) {
  const { t, tv, bad } = useEditor();
  const [difficulty, setDifficulty] = useState<PackMode>("");
  const [floor, setFloor] = useState(0);
  const [images, setImages] = useState(false);
  const [query, setQuery] = useState(""); // a part of a pack's name: only the packs that hold it show
  const searchBox = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState<string | null>(null);
  const lanes = lanesOf(plan);
  const line = lineAt(lanes, plan.threshold);
  const extra = Object.keys(plan.weights).filter((n) => !(n in data.packs)); // weighed, gone from the data file
  const matchesQuery = (n: string) => n.toLowerCase().includes(query.trim().toLowerCase());
  const shown = [...Object.keys(data.packs).filter((n) => onFloor(data.packs[n], difficulty, floor)), ...extra].filter(matchesQuery);
  useSlashFocus(searchBox); // as on the gift list tab
  const set = (patch: Partial<PackPlanValues>) => onChange?.({ ...plan, ...patch });
  const weigh = (what: string, w: number) => (what === UNLISTED ? set({ unlisted: w }) : set({ weights: { ...plan.weights, [what]: w } }));
  const lanesBox = useRef<HTMLDivElement>(null);
  const picks = usePackPicks(lanesBox, path, new Set(query.trim() ? shown : [...shown, UNLISTED]));
  const weightOfPack = (what: string) => (what === UNLISTED ? plan.unlisted : weightOf(plan, what));
  const signed = (w: number) => (w > 0 ? `+${w}` : String(w));
  /** Every pack of `names` to weight `w` in one change, read out. */
  const weighAll = (names: string[], w: number) => {
    const weights = { ...plan.weights };
    for (const n of names) if (n !== UNLISTED) weights[n] = w;
    set(names.includes(UNLISTED) ? { weights, unlisted: w } : { weights });
    picks.say(fill(t("packs.moved"), { n: names.length, w: signed(w) }));
  };
  // The pack whose weight is being typed: on its chip, or in a + lane for a new weight, the one above the lanes or below (#720).
  // PICKS types the weight of every pick, on the chip `on` or in a + lane.
  const [typing, setTyping] = useState<{ what: string; lane: AddAt | null; on?: string } | null>(null); // lane null: on the chip
  const ask = (what: string, lane: AddAt | null = null, on?: string) => setTyping({ what, lane, on });
  // A press in the lanes while a box is open (#739): the box's blur keeps its score, which moves packs before the button comes
  // up. A drag would then start from whatever is under the press by now, so none starts; the click lands on the lanes, not on
  // the pack pressed, so the lanes open it. "" is a press beside the packs; null, no box open at the press.
  const pressed = useRef<string | null>(null);
  const box = (what: string, current?: number) => (
    <WeightBox key={what /* a fresh box per pack: nothing typed carries over */} value={current}
      onDone={(w) => { if (w !== null) (what === PICKS ? weighAll(picks.picks, w) : weigh(what, w)); setTyping(null); }} />
  );
  const typingOn = (what: string) => typing?.lane === null && (typing.what === what || (typing.what === PICKS && typing.on === what));
  /** A click on a pack: with Ctrl it is picked or unpicked, with Shift the run up to it is picked; without, its box opens, for
   * every pick when it is one of several, else for it alone, and the picks go. */
  const activate = (what: string, e: MouseEvent) => {
    if (e.ctrlKey) picks.toggle(what);
    else if (e.shiftKey) { window.getSelection()?.removeAllRanges(); picks.extend(what); } // a Shift click selects text
    else {
      picks.anchorAt(what);
      if (picks.carried(what).length > 1) ask(PICKS, null, what);
      else { picks.clear(); ask(what); }
    }
  };
  // Alt+↑ / Alt+↓ on a pack (#743): it and every pick with it go to the lane above or below its own, or past the first or the
  // last lane to a new weight there, the one a + lane offers (nextScore). The focus stays on the pack.
  const step = (what: string, dir: -1 | 1) => {
    const i = lanes.indexOf(weightOfPack(what)) + dir;
    const w = i < 0 ? nextScore("top") : i >= lanes.length ? nextScore("bottom") : lanes[i];
    if (w === weightOfPack(what)) return; // +10 or -10 already: no lane past it
    picks.follow(what);
    weighAll(picks.carried(what), w);
  };
  const carrying = drag && drag !== LINE ? picks.carried(drag) : []; // what the drag moves
  const several = carrying.length > 1;
  const [over, setOver] = useState<number | null>(null); // the lane under a drag of several packs
  const dropOn = (w: number | AddAt) => (e: DragEvent) => {
    e.preventDefault();
    if (drag === LINE && typeof w === "number") set({ threshold: w });
    else if (drag && drag !== LINE) {
      if (typeof w !== "number") ask(several ? PICKS : drag, w);
      else if (several) weighAll(carrying, w);
      else weigh(drag, w);
    }
    setDrag(null); setOver(null);
  };
  const target = (accepts: boolean, w: number | AddAt) => (onChange && accepts
    ? { onDragOver: (e: DragEvent) => e.preventDefault(), onDrop: dropOn(w) } : {});
  const dropHover = (w: number) => (several ? {
    onDragOver: (e: DragEvent) => { e.preventDefault(); if (over !== w) setOver(w); },
    onDragLeave: (e: DragEvent) => { if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOver((o) => (o === w ? null : o)); },
  } : {});
  const dragged = (what: string) => (onChange && !typingOn(what) ? { // a box on a draggable chip would drag, not select its text
    draggable: true,
    onDragStart: (e: DragEvent) => {
      if (pressed.current !== null) { e.preventDefault(); return; }
      if (!picks.has(what)) picks.clear(); // a pack not picked moves alone
      setDrag(what); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", what);
    },
    onDragEnd: () => { setDrag(null); setOver(null); },
  } : {});
  const clickable = (what: string) => (!onChange ? {} : typingOn(what) ? {
    // a press on the chip around its box would blur the box, which closes it, and the click would open it again, empty
    onMouseDown: (e: MouseEvent) => { if (!(e.target instanceof HTMLInputElement)) e.preventDefault(); },
  } : {
    role: "button", tabIndex: 0, "aria-pressed": picks.has(what), onClick: (e: MouseEvent) => { pressed.current = null; activate(what, e); },
    onMouseDown: () => { if (pressed.current !== null) pressed.current = what; },
    onKeyDown: (e: KeyboardEvent) => {
      if (e.key === " ") { e.preventDefault(); picks.toggle(what); } // Enter opens the box
      else if (e.key === "Enter") { e.preventDefault(); if (picks.carried(what).length > 1) ask(PICKS, null, what); else ask(what); }
      else if (e.altKey && !e.ctrlKey && !e.metaKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) { e.preventDefault(); step(what, e.key === "ArrowUp" ? -1 : 1); }
    },
  });
  /** A pack's marks: picked; dimmed while a drag of several packs takes it, but for the pack held, which shows their count. */
  const pickClass = (what: string) => (picks.has(what) ? " picked" : "") + (several && carrying.includes(what) && what !== drag ? " lifted" : "");
  const pickMarks = (what: string) => <>
    {picks.has(what) && <span className="tick" aria-hidden>✓</span>}
    {drag === what && several && <span className="count" aria-hidden>{carrying.length}</span>}
  </>;
  // The line stops between two lanes, or under the last one (never refresh): gap g (1..lanes) sits under lane g-1, so its
  // threshold is that lane's weight.
  const toGap = (g: number) => set({ threshold: lanes[g - 1] });
  const uid = useId(); // the group titles' ids
  const chip = (name: string) => {
    const floors = data.packs[name] === undefined ? undefined : floorBadges(data.packs[name], t("packs.floorSep"));
    const cover = images ? coverOf(name) : undefined; // the card has its title printed on it: the name moves to the tooltip
    return (
      <span key={name} className={"pk" + (path && bad(`${path}/weights/${name}`) ? " bad" : "") + pickClass(name)} data-path={path && `${path}/weights/${name}`}
        data-pk={name} {...dragged(name)} {...clickable(name)} title={cover ? name : undefined}>
        {pickMarks(name)}
        {cover ? <img className="img" src={cover} alt={name} draggable={false} /> : images && <span className="img" aria-hidden />}
        {!cover && <span className="nm">{name}</span>}
        {floors
          ? floors.map((f) => {
            const label = `${t(BADGES[f.mode][0])} ${f.text}`;
            return <small key={f.mode} className={"fl" + BADGES[f.mode][1]} role="img" title={label} aria-label={label}>{f.text}</small>;
          })
          : <small><em>{t("packNotInData")}</em></small>}
        {typingOn(name) && box(typing!.what, weightOf(plan, name))}
      </span>
    );
  };
  const lineBar = (
    <div className={"thr" + (path && bad(`${path}/threshold`) ? " bad" : "")} data-path={path && `${path}/threshold`} {...dragged(LINE)}>
      <span>{t("packs.threshold").replace("{n}", String(plan.threshold))}</span>
      {onChange && <>
        <button type="button" className="icon" aria-label={t("up")} title={t("up")} disabled={line - 1 < 1}
          onClick={() => toGap(line - 1)}>↑</button>
        <button type="button" className="icon" aria-label={t("down")} title={t("down")} disabled={line + 1 > lanes.length}
          onClick={() => toGap(line + 1)}>↓</button>
      </>}
    </div>
  );
  const gapOrLine = (g: number) => (g === line ? lineBar : <div className="gap" {...target(drag === LINE, lanes[g - 1])} />);
  // A + lane's box opens on the next score past the lanes, one above the highest or one below the lowest (#734), in range.
  const nextScore = (at: AddAt) => Math.min(WEIGHT_MAX, Math.max(WEIGHT_MIN, at === "top" ? lanes[0] + 1 : lanes[lanes.length - 1] - 1));
  const addLane = (at: AddAt) => onChange && (
    <div className="lane add" {...target(drag !== null && drag !== LINE, at)}>
      {typing?.lane === at
        ? <>＋ {typing.what === PICKS ? fill(t("packs.many"), { n: picks.picks.length }) : typing.what === UNLISTED ? t("packs.unlisted") : typing.what} {box(typing.what, nextScore(at))}</>
        : <>＋ {t("packs.newLane")}</>}
    </div>
  );
  const chips = <T extends string | number>(values: T[], value: T, label: (v: T) => string, pick: (v: T) => void, cls?: (v: T) => string) =>
    values.map((v) => (
      <button type="button" key={String(v)} className={"chip" + (cls ? cls(v) : "")} aria-pressed={v === value} onClick={() => pick(v)}>{label(v)}</button>
    ));
  return (<>
    <div className="packbar">
      <input ref={searchBox} type="search" className="pk-search" aria-label={t("packs.search")} placeholder={t("packs.search_ph")}
        value={query} onChange={(e) => setQuery(e.target.value)}
        onKeyDown={(e) => { if (e.key === "Escape" && query) { e.preventDefault(); setQuery(""); } }} />
      <span className="seg">
        {chips<PackMode>(["", "normal", "hard", "infinity", "extreme"], difficulty,
          (v) => (v ? t(BADGES[MODE_KEYS[v]][0]) : t("packs.anyDifficulty")) /* a badge's name: 普通, not NORMAL, in Chinese */, setDifficulty,
          (v) => (v ? " mode" + BADGES[MODE_KEYS[v]][1] : "")) /* and its colour */}
      </span>
      <span className="seg view">
        {chips([false, true].map(String), String(images), (v) => t(v === "true" ? "packs.images" : "packs.names"), (v) => setImages(v === "true"))}
      </span>
      <span className="seg floors">
        {chips(FLOORS, floor, (v) => (v ? t("packs.floor").replace("{n}", String(v)) : t("packs.anyFloor")), setFloor)}
      </span>
    </div>
    {onChange && <p className="muted">{withBreaks(t("packs.hint"))}</p>}
    <p className="muted floorkey">
      {Object.values(BADGES).map(([key, cls]) => <small key={key} className={"fl" + cls}>{t(key)}</small>)}{t("packs.floorsKey")}
    </p>
    {onChange && (
      // the same height picked or not, so a Ctrl click never moves the packs under the next one; held at the top while the page scrolls
      <div className={"pickbar" + (picks.picks.length ? " on" : "")}>
        {picks.picks.length ? <>
          <b>{fill(t("packs.picked"), { n: picks.picks.length })}</b>
          <span className="names">{picks.picks.map((n) => (n === UNLISTED ? t("packs.unlisted") : n)).join(t("packs.floorSep"))}</span>
          <span className="keys">{t("packs.pickedKeys")}</span>
          <button type="button" onClick={picks.clear}>{t("packs.unpick")}</button>
        </> : <span className="muted">{t("packs.pickHint")}</span>}
      </div>
    )}
    <div ref={lanesBox} className={"lanes" + (images ? " images" : "") + (drag === LINE ? " moving" : drag ? " carrying" : "") + (picks.drawing ? " boxing" : "")}
      onMouseDownCapture={(e) => { pressed.current = typing && e.button === 0 ? "" : null; }}
      onClick={(e) => { const p = pressed.current; pressed.current = null; if (p) activate(p, e); }} {...(onChange ? picks.onLanes : {})}>
      {picks.marquee}
      {addLane("top")}
      {line === 0 && lineBar}
      {lanes.map((w, i) => {
        const inLane = shown.filter((n) => weightOf(plan, n) === w);
        const groups = packGroups(inLane, data.packs, difficulty); // a long lane split by difficulty (#742), after the filters and the search
        return <Fragment key={w}>
          {i > 0 && gapOrLine(i)}
          <div className={"lane" + (over === w && several ? " lit" : "")} {...target(drag !== LINE, w)} {...dropHover(w)}>
            <span className={"w" + (w > 0 ? " pos" : w < 0 ? " neg" : "")}>{signed(w)}</span>
            <div className={"packs" + (groups ? " grouped" : "")}>
              {groups?.map(({ group, names }) => {
                const { title, note } = GROUPS[group];
                const id = `${uid}${w}${group}`;
                return (
                  <section key={group} className="pg" aria-labelledby={id}>
                    <h3 id={id}>
                      <span className="t">{t(title)}</span><span className="n">{names.length}</span>
                      {note && <small>{fill(t(note), { n: MODE_BANDS.X.join("–") })}</small>}
                    </h3>
                    <div className="pgp">{names.map(chip)}</div>
                  </section>
                );
              }) ?? inLane.map(chip)}
              {w === plan.unlisted && !query.trim() && (
                <span className={"pk unlisted" + (path && bad(`${path}/unlisted`) ? " bad" : "") + pickClass(UNLISTED)} data-path={path && `${path}/unlisted`}
                  data-pk={UNLISTED} {...dragged(UNLISTED)} {...clickable(UNLISTED)}>
                  {pickMarks(UNLISTED)}
                  {images && <span className="img" aria-hidden />}
                  <span className="nm">{t("packs.unlisted")}</span>
                  {typingOn(UNLISTED) && box(typing!.what, plan.unlisted)}
                </span>
              )}
            </div>
            {over === w && several && <span className="droplabel">{fill(t("packs.drop"), { n: carrying.length, w: signed(w) })}</span>}
          </div>
        </Fragment>;
      })}
      {gapOrLine(lanes.length)}
      {addLane("bottom")}
    </div>
    {picks.readOut}
    <Field label={t("packs.eventPacks")} path={path && `${path}/event_packs`} note={t("packs.eventPacksNote")}>
      {onChange
        ? <Select value={plan.event_packs} options={EVENT_MODES} label={(v) => tv("event_packs", v)} onChange={(v) => set({ event_packs: v })} />
        : <span>{tv("event_packs", plan.event_packs)}</span>}
    </Field>
  </>);
}
