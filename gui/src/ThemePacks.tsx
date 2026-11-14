// Theme pack plans (spec 04 section 8): lanes of weights with the refresh threshold between them, and the locked default plan
// above the user's own.
import { Fragment, useEffect, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent } from "react";
import { loadThemePacks } from "./api";
import { GIFT_BY_ID } from "./giftCatalog";
import { listsOfPlan, packWanted } from "./gifts";
import { fill, localName } from "./i18n";
import {
  EVENT_MODES, MODE_KEYS, WEIGHT_MAX, WEIGHT_MIN, floorBadges, lanesOf, lineAt, newPackPlan, onFloor, parseThemePacks, weightOf,
  type PackMode, type PackPlanValues, type ThemePackPlan, type ThemePacks,
} from "./model";
import { PlanTab } from "./Plans";
import { Field, Select, useEditor, useSlashFocus, withBreaks } from "./ui";
import { webpFolder } from "./webpFolder";

export function ThemePackTab() {
  const { t } = useEditor();
  const [data, setData] = useState<ThemePacks>(() => parseThemePacks(""));
  const [error, setError] = useState("");
  useEffect(() => { loadThemePacks().then(setData, (e) => setError(String(e))); }, []);
  const note = error && <p className="bad">{t("themePacksError")}: {error}</p>;
  return (
    <PlanTab<ThemePackPlan> planKey="theme_pack_plans" tab="tab.themepacks" make={newPackPlan}
      lead={{ id: "default", label: t("defaultPlanLocked"), body: <>
        <p className="muted">{t("defaultPlanNote")}</p>{note}
        <PackPlanEditor data={data} plan={data.default_plan} planId="default" path="" />
      </> }}
      editor={(p, change, path) => <>
        {note}
        <PackPlanEditor data={data} plan={p} planId={p.id} path={path} onChange={(v) => change({ ...p, ...v })} />
      </>} />
  );
}

// #241's cards (theme_pack_covers/index.json: pack name -> file); a pack without one, or a build before they exist, shows
// its name on a blank card. The title is printed on the card, so the name is the tooltip.
const coverOf = webpFolder(
  import.meta.glob<string>("../../assets/resource/base/data/theme_pack_covers/*.webp", { eager: true, query: "?url", import: "default" }),
  import.meta.glob<Record<string, string>>("../../assets/resource/base/data/theme_pack_covers/index.json", { eager: true, import: "default" }),
);

const UNLISTED = "\u0000unlisted"; // what the "unlisted packs" chip drags: no pack name starts with NUL
const LINE = "\u0000line";
/** The two + lanes a pack is dropped on for a new weight: above the lanes and below them (#720). */
type AddAt = "top" | "bottom";
/** The floor filter's chips (0: any): a run's 15 floors, 6-10 INFINITY's and 11-15 EXTREME's (#387). */
const FLOORS = Array.from({ length: 16 }, (_, i) => i);
/** A floor badge's label and class per mode of the data file. */
const BADGES = {
  N: ["packs.floorsNormal", ""], H: ["packs.floorsHard", " hard"], I: ["packs.floorsInfinity", " inf"], X: ["packs.floorsExtreme", " ext"],
} as const;

/** A pack's weight typed in place (#679, in place of prompt()): Enter keeps a whole number from -10 to 10, or says why not
 * beside the box; Esc, or leaving the box, keeps the weight as it was. The weight it opens on is selected, so a number typed
 * replaces it (#734). */
function WeightBox({ value, onDone }: { value?: number; onDone: (w: number | null) => void }) {
  const { t } = useEditor();
  const [text, setText] = useState(value === undefined ? "" : String(value));
  const [wrong, setWrong] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => { input.current?.select(); }, []);
  const keep = () => {
    const w = Number(text);
    if (text.trim() !== "" && Number.isInteger(w) && w >= WEIGHT_MIN && w <= WEIGHT_MAX) onDone(w);
    else setWrong(true);
  };
  return (
    <span className="weigh">
      <input ref={input} type="number" min={WEIGHT_MIN} max={WEIGHT_MAX} step={1} autoFocus aria-label={t("packs.weightPrompt")} value={text}
        onChange={(e) => { setText(e.target.value); setWrong(false); }} onBlur={() => onDone(null)}
        onKeyDown={(e) => {
          if (e.key === "Enter") { e.preventDefault(); keep(); }
          if (e.key === "Escape") onDone(null);
        }} />
      {wrong && <small>{t("packs.weightRange")}</small>}
    </span>
  );
}

/** Design A of #240: one lane per weight in use (0 always), highest first, and the threshold line between lanes.
 * Drag a pack to another lane, or onto + for a new weight; click one to type its weight. Read-only without onChange. */
function PackPlanEditor({ data, plan, planId, path, onChange }: {
  data: ThemePacks; plan: PackPlanValues; planId: string; path: string; onChange?: (p: PackPlanValues) => void;
}) {
  const { s, t, tv, bad, zh } = useEditor();
  const lists = listsOfPlan(planId, s.teams, s.gift_lists);
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
  // The pack whose weight is being typed: on its chip, or in a + lane for a new weight, the one above the lanes or below (#720).
  const [typing, setTyping] = useState<{ what: string; lane: AddAt | null } | null>(null); // lane null: on the chip
  const ask = (what: string, lane: AddAt | null = null) => setTyping({ what, lane });
  const box = (what: string, current?: number) => (
    <WeightBox value={current} onDone={(w) => { if (w !== null) weigh(what, w); setTyping(null); }} />
  );
  const typingOn = (what: string) => typing?.what === what && typing.lane === null;
  const dropOn = (w: number | AddAt) => (e: DragEvent) => {
    e.preventDefault();
    if (drag === LINE && typeof w === "number") set({ threshold: w });
    else if (drag && drag !== LINE) (typeof w === "number" ? weigh(drag, w) : ask(drag, w));
    setDrag(null);
  };
  const target = (accepts: boolean, w: number | AddAt) => (onChange && accepts
    ? { onDragOver: (e: DragEvent) => e.preventDefault(), onDrop: dropOn(w) } : {});
  const dragged = (what: string) => (onChange && !typingOn(what) ? { // a box on a draggable chip would drag, not select its text
    draggable: true,
    onDragStart: (e: DragEvent) => { setDrag(what); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", what); },
    onDragEnd: () => setDrag(null),
  } : {});
  const clickable = (what: string) => (!onChange ? {} : typingOn(what) ? {
    // a press on the chip around its box would blur the box, which closes it, and the click would open it again, empty
    onMouseDown: (e: MouseEvent) => { if (!(e.target instanceof HTMLInputElement)) e.preventDefault(); },
  } : {
    role: "button", tabIndex: 0, onClick: () => ask(what),
    onKeyDown: (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ask(what); } },
  });
  // The line stops between two lanes, or under the last one (never refresh): gap g (1..lanes) sits under lane g-1, so its
  // threshold is that lane's weight.
  const toGap = (g: number) => set({ threshold: lanes[g - 1] });
  const chip = (name: string) => {
    const floors = data.packs[name] === undefined ? undefined : floorBadges(data.packs[name], t("packs.floorSep"));
    const cover = images ? coverOf(name) : undefined; // the card has its title printed on it: the name moves to the tooltip
    const wanted = packWanted(lists, data.pack_ids[name]).map((id) => GIFT_BY_ID.get(id)).filter((g) => g !== undefined)
      .map((g) => localName(g, zh));
    const isWanted = wanted.length > 0;
    const wantedTip = fill(t("packs.wantedTip"), { names: wanted.join(t("gl.sep")) });
    // The whole chip shows the wanted gifts on hover, the dot being too small a target (#720).
    const tip = [cover ? name : "", isWanted ? wantedTip : ""].filter(Boolean).join("\n") || undefined;
    return (
      <span key={name} className={"pk" + (path && bad(`${path}/weights/${name}`) ? " bad" : "")} data-path={path && `${path}/weights/${name}`}
        {...dragged(name)} {...clickable(name)} title={tip}>
        {cover ? <img className="img" src={cover} alt={name} draggable={false} /> : images && <span className="img" aria-hidden />}
        {!cover && <span className="nm">{name}</span>}
        {floors
          ? floors.map((f) => {
            const label = `${t(BADGES[f.mode][0])} ${f.text}`;
            return <small key={f.mode} className={"fl" + BADGES[f.mode][1]} role="img" title={label} aria-label={label}>{f.text}</small>;
          })
          : <small><em>{t("packNotInData")}</em></small>}
        {isWanted && <i className="wd" role="img" aria-label={t("packs.wanted")} title={wantedTip} />}
        {typingOn(name) && box(name, weightOf(plan, name))}
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
        ? <>＋ {typing.what === UNLISTED ? t("packs.unlisted") : typing.what} {box(typing.what, nextScore(at))}</>
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
    <p className="muted floorkey"><i className="wd" aria-hidden />{t("packs.wantedKey")}</p>
    <div className={"lanes" + (images ? " images" : "") + (drag === LINE ? " moving" : drag ? " carrying" : "")}>
      {addLane("top")}
      {line === 0 && lineBar}
      {lanes.map((w, i) => (
        <Fragment key={w}>
          {i > 0 && gapOrLine(i)}
          <div className="lane" {...target(drag !== LINE, w)}>
            <span className={"w" + (w > 0 ? " pos" : w < 0 ? " neg" : "")}>{w > 0 ? `+${w}` : w}</span>
            <div className="packs">
              {shown.filter((n) => weightOf(plan, n) === w).map(chip)}
              {w === plan.unlisted && !query.trim() && (
                <span className={"pk unlisted" + (path && bad(`${path}/unlisted`) ? " bad" : "")} data-path={path && `${path}/unlisted`}
                  {...dragged(UNLISTED)} {...clickable(UNLISTED)}>
                  {images && <span className="img" aria-hidden />}
                  <span className="nm">{t("packs.unlisted")}</span>
                  {typingOn(UNLISTED) && box(UNLISTED, plan.unlisted)}
                </span>
              )}
            </div>
          </div>
        </Fragment>
      ))}
      {gapOrLine(lanes.length)}
      {addLane("bottom")}
    </div>
    <Field label={t("packs.eventPacks")} path={path && `${path}/event_packs`} note={t("packs.eventPacksNote")}>
      {onChange
        ? <Select value={plan.event_packs} options={EVENT_MODES} label={(v) => tv("event_packs", v)} onChange={(v) => set({ event_packs: v })} />
        : <span>{tv("event_packs", plan.event_packs)}</span>}
    </Field>
  </>);
}
