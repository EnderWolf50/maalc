// Named plans (spec 04 sections 6–8) and the editors teams reuse for their custom values.
import { Fragment, useEffect, useId, useRef, useState, type DragEvent, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { loadThemePacks } from "./api";
import {
  EVENT_MODES, GRACES, LEVELS, MODE_KEYS, SINNERS, buyOrder, clickCard, clickEnhance, defaultStarlight, enhanceAll, floorBadges, freeName,
  gracePrice,
  lanesOf, lineAt, newId, newPackPlan, onFloor, parseThemePacks, selectAll, starlightCost, toggleSinner, weightOf,
  type DeploymentPlan, type Order, type PackMode, type PackPlanValues, type StarlightPlan, type StarlightValues, type ThemePackPlan,
  type Grace, type Team, type ThemePacks,
} from "./model";
import { GIFT_BY_ID, giftName } from "./giftCatalog";
import { listsOfPlan, packWanted } from "./gifts";
import { effectLines } from "./graceText";
import { fill } from "./i18n";
import { Field, Input, Mark, ReorderList, Select, useEditor, usePick, useSlashFocus, useUndo, withBreaks, type PlanKey } from "./ui";

/** The 12 sinners in the game's grid; clicking adds one at the end of the order or leaves it out
 * (spec 04 section 6). Read-only without onChange. */
export function SinnerGrid({ order, onChange, path }: { order: Order; onChange?: (o: Order) => void; path: string }) {
  const { t, bad } = useEditor();
  return (<>
    {onChange && <p className="muted">{t("order.hint")}</p>}
    <div className={"sinners" + (onChange ? "" : " readonly") + (bad(path) ? " bad" : "")} data-path={path}>
      {SINNERS.map((s) => {
        const n = order.indexOf(s) + 1;
        const kind = n === 0 ? "" : n <= 7 ? "deployed" : "backup";
        return (
          <button type="button" key={s} className={"sinner " + kind} disabled={!onChange} aria-pressed={n > 0}
            onClick={() => onChange?.(toggleSinner(order, s))}>
            {n > 0 && <span className="num">{n}</span>}
            {n > 0 && <span className="banner">{t(n <= 7 ? "order.deployed" : "order.backup")}</span>}
            <span className="name">{s}</span>
          </button>
        );
      })}
    </div>
  </>);
}

/** The game's "Grace of the Star" page: click a card to select it at base, + / ++ to enhance it
 * (spec 04 section 7). The number on a selected card is its place in the buying order. Read-only without onChange. */
export function StarlightEditor({ value, onChange, path }: {
  value: StarlightValues; onChange?: (v: StarlightValues) => void; path: string;
}) {
  const { s, t, tv, bad } = useEditor();
  const zh = s.language === "zh_tw";
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
            <div key={g.en} className={`grace ${level}`} role="group" aria-label={graceName(g, zh)}
              aria-disabled={!onChange} title={`${n}. ${g.en} (${tv("level", level)})`}
              onClick={() => set((v) => clickCard(v, n))}>
              {rank > 0 && <span className="rank" id={`${id}-rank-${n}`}>{rank}</span>}
              <span className="price" id={`${id}-price-${n}`}>★ {gracePrice(n, level === "none" ? "base" : level)}</span>
              <div className="head">
                <img className="icon" src={GRACE_ICONS[`./grace_icons/${n}.webp`]} alt="" />
                <button type="button" className="name" disabled={!onChange} aria-pressed={rank > 0} aria-label={graceName(g, zh)}
                  aria-describedby={[rank > 0 && `${id}-rank-${n}`, `${id}-price-${n}`, zh && `${id}-fx-${n}`].filter(Boolean).join(" ")}>
                  <span className="title">{graceName(g, zh)}{plusOf(level)}</span>
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
                    aria-label={`${graceName(g, zh)} ${"+".repeat(plus)}`}
                    onClick={(e) => { e.stopPropagation(); set((v) => clickEnhance(v, n, plus)); }}>{"+".repeat(plus)}</button>
                ))}
              </span>
            </div>
          );
        })}
      </div>
      <div className="grace-side">
        {onChange && <>
          {/* lit while a second click would undo them: every card selected, every card at + or at ++ */}
          <button type="button" aria-pressed={!value.levels.includes("none")} onClick={() => set(selectAll)}>{t("starlight.selectAll")}</button>
          <span className="muted">{t("starlight.enhanceAll")}</span>
          {([1, 2] as const).map((plus) => (
            <button type="button" key={plus} className="boost" aria-label={`${t("starlight.enhanceAll")} ${"+".repeat(plus)}`}
              aria-pressed={value.levels.every((l) => l === LEVELS[plus + 1])} onClick={() => set((v) => enhanceAll(v, plus))}>
              {"+".repeat(plus)}
            </button>
          ))}
        </>}
        <span className="total">{t("starlight.total")} <b>★ {starlightCost(value.levels)}</b></span>
        <Mark as="label" className="check" path={`${path}/convert_leftover`}>
          <Input type="checkbox" checked={value.convert_leftover} disabled={!onChange}
            onChange={(e) => set((v) => ({ ...v, convert_leftover: e.target.checked }))} />
          {t("starlight.convert_leftover")}
        </Mark>
      </div>
    </div></>
  );
}

/** The plan a team names for each kind (null: its own custom values). */
const PLAN_OF: Record<PlanKey, (team: Team) => string | null> = {
  deployment_order_plans: (x) => ("plan" in x.deployment_order ? x.deployment_order.plan : null),
  starlight_plans: (x) => ("plan" in x.starlight ? x.starlight.plan : null),
  theme_pack_plans: (x) => x.theme_pack_plan,
};

/** Which teams use plan `id`, so a change or a delete shows whom it touches. */
function PlanUsers({ planKey, id }: { planKey: PlanKey; id: string }) {
  const { s, t } = useEditor();
  const names = s.teams.filter((x) => PLAN_OF[planKey](x) === id).map((x) => x.name || "—");
  return <p className="muted">{names.length ? fill(t("plan.usedBy"), { names: names.join(t("gl.sep")) }) : t("plan.unused")}</p>;
}

/** A grace's name in the GUI's language: the Chinese one when the data has it. */
const graceName = (g: Grace, zh: boolean) => (zh && g.zh ? g.zh : g.en);
/** The game's icon of each grace, ./grace_icons/<n>.webp (tools/grace_icons.py). */
const GRACE_ICONS = import.meta.glob<string>("./grace_icons/*.webp", { eager: true, query: "?url", import: "default" });
/** What the game adds to a grace's title at a level: "+" at +, "++" at ++, nothing below. */
const plusOf = (level: string) => "+".repeat(Math.max(0, LEVELS.indexOf(level) - 1));

/** A starlight plan on one line, for a team that uses it: the picks in buying order with their level, and the total. */
export function StarlightReceipt({ value }: { value: StarlightValues }) {
  const { s, t } = useEditor();
  const zh = s.language === "zh_tw";
  const order = buyOrder(value);
  return (
    <div className="receipt">
      {order.length ? (
        <ol>
          {order.map((n, i) => {
            const g = GRACES[n - 1], level = value.levels[n - 1];
            return <li key={n}><b>{i + 1}</b>{graceName(g, zh)}{level !== "base" && <i>{plusOf(level)}</i>}</li>;
          })}
        </ol>
      ) : <span className="muted">{t("starlight.none")}</span>}
      <span className="total">{t("starlight.total")} <b>★ {starlightCost(value.levels)}</b></span>
    </div>
  );
}

/** A list of named plans on the left, the selected plan's editor on the right; `lead`, a read-only plan above the list. */
function PlanTab<P extends { id: string; name: string }>({ planKey, tab, make, editor, lead }: {
  planKey: PlanKey; tab: "tab.deployment" | "tab.starlight" | "tab.themepacks"; make: () => Omit<P, "id" | "name">;
  editor: (plan: P, change: (p: P) => void, path: string) => ReactNode;
  lead?: { id: string; label: string; body: ReactNode };
}) {
  const { s, update, t, bad } = useEditor();
  const plans = s[planKey] as unknown as P[];
  const [i, setSel] = usePick(planKey, plans, lead?.id); // -1: the lead
  const [undoNote, removeAt] = useUndo();
  const set = (fn: (list: P[]) => void) => update((d) => fn(d[planKey] as unknown as P[]));
  const remove = () => removeAt(plans, i, set, setSel);
  const add = () => {
    const id = newId();
    set((list) => list.push({ ...make(), id, name: freeName(t(tab), plans.map((p) => p.name)) } as P));
    setSel(id);
  };
  return (
    <div className="split">
      <aside>
        {lead && <button type="button" className={"lead" + (i === -1 ? " selected" : "")} onClick={() => setSel(lead.id)}>{lead.label}</button>}
        {plans.length || lead ? (
          <ReorderList items={plans} keyOf={(p) => p.id} selected={i} onSelect={(j, list) => setSel(list[j].id)}
            badAt={(j) => bad(`${planKey}/${j}`)} onChange={(list) => set((l) => l.splice(0, l.length, ...list))}
            render={(p) => p.name || "—"} />
        ) : <p className="muted">{t("noPlans")}</p>}
        {undoNote}
        <button type="button" onClick={add}>+ {t("add")}</button>
      </aside>
      <section data-path={i >= 0 ? `${planKey}/${i}` : undefined}>
        {i === -1 && lead ? <><PlanUsers planKey={planKey} id={lead.id} />{lead.body}</> : plans[i] && (
          <>
            <div className="row">
              <Field label={t("name")} path={`${planKey}/${i}/name`}>
                <Input value={plans[i].name} onChange={(e) => set((l) => { l[i].name = e.target.value; })} />
              </Field>
              <button type="button" className="danger" onClick={remove}>
                {t("remove")}
              </button>
            </div>
            <PlanUsers planKey={planKey} id={plans[i].id} />
            {editor(plans[i], (p) => set((l) => { l[i] = p; }), `${planKey}/${i}`)}
          </>
        )}
      </section>
    </div>
  );
}

export const DeploymentTab = () => (
  <PlanTab<DeploymentPlan> planKey="deployment_order_plans" tab="tab.deployment" make={() => ({ order: [...SINNERS] })}
    editor={(p, change, path) => <SinnerGrid order={p.order} path={`${path}/order`} onChange={(order) => change({ ...p, order })} />} />
);

export const StarlightTab = () => (
  <PlanTab<StarlightPlan> planKey="starlight_plans" tab="tab.starlight" make={defaultStarlight}
    editor={(p, change, path) => (
      <StarlightEditor value={p} path={path} onChange={(v) => change({ ...p, ...v })} />
    )} />
);

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

// #241's cards (theme_pack_covers/index.json: pack name -> file), bundled at build time; a pack without one, or a
// build before they exist, shows its name on a blank card. The title is printed on the card, so the name is the tooltip.
const COVERS_DIR = "../../assets/resource/base/data/theme_pack_covers/";
const COVER_URLS = import.meta.glob<string>("../../assets/resource/base/data/theme_pack_covers/*.webp",
  { eager: true, query: "?url", import: "default" });
const COVER_INDEX = Object.values(import.meta.glob<Record<string, string>>("../../assets/resource/base/data/theme_pack_covers/index.json",
  { eager: true, import: "default" }))[0] ?? {};
const coverOf = (name: string): string | undefined => COVER_URLS[COVERS_DIR + COVER_INDEX[name]];

const UNLISTED = "\u0000unlisted"; // what the "unlisted packs" chip drags: no pack name starts with NUL
const LINE = "\u0000line";
/** The floor filter's chips (0: any): a run's 15 floors, 6-10 INFINITY's and 11-15 EXTREME's (#387). */
const FLOORS = Array.from({ length: 16 }, (_, i) => i);
/** A floor badge's label and class per mode of the data file. */
const BADGES = {
  N: ["packs.floorsNormal", ""], H: ["packs.floorsHard", " hard"], I: ["packs.floorsInfinity", " inf"], X: ["packs.floorsExtreme", " ext"],
} as const;

/** A pack's weight typed in place (#679, in place of prompt()): Enter keeps a whole number from -10 to 10, or says why not
 * beside the box; Esc, or leaving the box, keeps the weight as it was. */
function WeightBox({ value, onDone }: { value?: number; onDone: (w: number | null) => void }) {
  const { t } = useEditor();
  const [text, setText] = useState(value === undefined ? "" : String(value));
  const [wrong, setWrong] = useState(false);
  const keep = () => {
    const w = Number(text);
    if (text.trim() !== "" && Number.isInteger(w) && w >= -10 && w <= 10) onDone(w);
    else setWrong(true);
  };
  return (
    <span className="weigh">
      <input type="number" min={-10} max={10} step={1} autoFocus aria-label={t("packs.weightPrompt")} value={text}
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
  const { s, t, tv, bad } = useEditor();
  const lists = listsOfPlan(planId, s.teams, s.gift_lists);
  const zh = s.language === "zh_tw";
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
  // The pack whose weight is being typed: on its chip, or in the + lane for a new weight (`lane`).
  const [typing, setTyping] = useState<{ what: string; lane: boolean } | null>(null);
  const ask = (what: string, lane = false) => setTyping({ what, lane });
  const box = (what: string, current?: number) => (
    <WeightBox value={current} onDone={(w) => { if (w !== null) weigh(what, w); setTyping(null); }} />
  );
  const typingOn = (what: string) => typing?.what === what && !typing.lane;
  const dropOn = (w: number | null) => (e: DragEvent) => {
    e.preventDefault();
    if (drag === LINE && w !== null) set({ threshold: w });
    else if (drag && drag !== LINE) (w === null ? ask(drag, true) : weigh(drag, w));
    setDrag(null);
  };
  const target = (accepts: boolean, w: number | null) => (onChange && accepts
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
      .map((g) => giftName(g, zh));
    const wantedTip = fill(t("packs.wantedTip"), { names: wanted.join(t("gl.sep")) });
    return (
      <span key={name} className={"pk" + (path && bad(`${path}/weights/${name}`) ? " bad" : "")} data-path={path && `${path}/weights/${name}`}
        {...dragged(name)} {...clickable(name)} title={cover ? name : undefined}>
        {cover ? <img className="img" src={cover} alt={name} draggable={false} /> : images && <span className="img" aria-hidden />}
        {!cover && <span className="nm">{name}</span>}
        {floors
          ? floors.map((f) => {
            const label = `${t(BADGES[f.mode][0])} ${f.text}`;
            return <small key={f.mode} className={"fl" + BADGES[f.mode][1]} role="img" title={label} aria-label={label}>{f.text}</small>;
          })
          : <small><em>{t("packNotInData")}</em></small>}
        {wanted.length > 0 && <small className="wk" role="img" title={wantedTip} aria-label={wantedTip}>{t("packs.wanted")}</small>}
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
    <div className={"lanes" + (images ? " images" : "") + (drag === LINE ? " moving" : "")}>
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
      {onChange && (
        <div className="lane add" {...target(drag !== null && drag !== LINE, null)}>
          {typing?.lane
            ? <>＋ {typing.what === UNLISTED ? t("packs.unlisted") : typing.what} {box(typing.what)}</>
            : <>＋ {t("packs.newLane")}</>}
        </div>
      )}
    </div>
    <Field label={t("packs.eventPacks")} path={path && `${path}/event_packs`} note={t("packs.eventPacksNote")}>
      {onChange
        ? <Select value={plan.event_packs} options={EVENT_MODES} label={(v) => tv("event_packs", v)} onChange={(v) => set({ event_packs: v })} />
        : <span>{tv("event_packs", plan.event_packs)}</span>}
    </Field>
  </>);
}
