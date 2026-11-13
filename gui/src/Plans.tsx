// Named plans (spec 04 sections 6–8) and the editors teams reuse for their custom values.
import { Fragment, useEffect, useState, type DragEvent, type KeyboardEvent, type MouseEvent, type ReactNode } from "react";
import { loadThemePacks } from "./api";
import {
  EVENT_MODES, GRACES, LEVELS, MODE_KEYS, SINNERS, buyOrder, clickCard, clickEnhance, defaultStarlight, enhanceAll, floorBadges, freeName,
  gracePrice,
  lanesOf, lineAt, newId, newPackPlan, onFloor, parseThemePacks, selectAll, starlightCost, toggleSinner, weightOf,
  type DeploymentPlan, type Order, type PackMode, type PackPlanValues, type StarlightPlan, type StarlightValues, type ThemePackPlan,
  type Team, type ThemePacks,
} from "./model";
import { GIFT_BY_ID, giftName } from "./giftCatalog";
import { listsOfPlan, packWanted } from "./gifts";
import { fill } from "./i18n";
import { Note, Row } from "./frame";
import { Field, GLYPHS, Icon, ReorderList, Select, useEditor, usePick, useUndo, type PlanKey } from "./ui";

/** The 12 sinners in the game's grid; clicking adds one at the end of the order or leaves it out
 * (spec 04 section 6). Read-only without onChange. */
export function SinnerGrid({ order, onChange, path }: { order: Order; onChange?: (o: Order) => void; path: string }) {
  const { t, bad } = useEditor();
  return (<>
    <p className="muted hint">{onChange ? t("order.hint") : t("plan.readonly")}</p>
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
  return (
    <><p className="muted hint">{onChange ? t("starlight.hint") : t("plan.readonly")}</p>
    <div className={"starlight" + (onChange ? "" : " readonly")} data-path={path}>
      <div className={"graces" + (bad(`${path}/levels`) || bad(`${path}/priority`) ? " bad" : "")}>
        {GRACES.map((g, i) => {
          const n = i + 1;
          const level = value.levels[i];
          const rank = order.indexOf(n) + 1;
          const effects = g.effects[level as "plus" | "plus2"] ?? g.effects.base;
          return (
            <div key={g.en} className={`grace ${level}`} role="button" tabIndex={onChange ? 0 : -1} aria-pressed={rank > 0}
              aria-disabled={!onChange} title={`${n}. ${g.en} (${tv("level", level)})`}
              onClick={() => set((v) => clickCard(v, n))}
              onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); set((v) => clickCard(v, n)); } }}>
              {rank > 0 && <span className="rank">{rank}</span>}
              <span className="price">★ {gracePrice(n, level === "none" ? "base" : level)}</span>
              <span className="name">{zh && g.zh ? g.zh : g.en}{zh && g.zh && <small>{g.en}</small>}</span>
              {zh && <ul>{effects.map((line, j) => <li key={j} className={line.startsWith("-") ? "sub" : ""}>{line.replace(/^-/, "")}</li>)}</ul>}
              <span className="enhance">
                {([1, 2] as const).map((plus) => (
                  <button type="button" key={plus} disabled={!onChange} aria-pressed={level === LEVELS[plus + 1]}
                    className={level === LEVELS[plus + 1] ? "lit" : ""}
                    onClick={(e) => { e.stopPropagation(); set((v) => clickEnhance(v, n, plus)); }}>{"+".repeat(plus)}</button>
                ))}
              </span>
            </div>
          );
        })}
      </div>
      <div className="grace-side">
        {onChange && <>
          <button type="button" onClick={() => set(selectAll)}>{t("starlight.selectAll")}</button>
          <span className="side-label">{t("starlight.enhanceAll")}</span>
          <button type="button" onClick={() => set((v) => enhanceAll(v, 1))}>+</button>
          <button type="button" onClick={() => set((v) => enhanceAll(v, 2))}>++</button>
        </>}
        <span className="total">{t("starlight.total")} <b>★ {starlightCost(value.levels)}</b></span>
        <label className="check">
          <input type="checkbox" checked={value.convert_leftover} disabled={!onChange}
            onChange={(e) => set((v) => ({ ...v, convert_leftover: e.target.checked }))} />
          {t("starlight.convert_leftover")}
        </label>
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
        <button type="button" className="add" onClick={add}>+ {t("add")}</button>
        {lead && <button type="button" className={"lead" + (i === -1 ? " selected" : "")} aria-current={i === -1 ? "true" : undefined}
          onClick={() => setSel(lead.id)}>{lead.label}</button>}
        {plans.length || lead ? (
          <ReorderList items={plans} keyOf={(p) => p.id} selected={i} onSelect={(j, list) => setSel(list[j].id)} label={t(tab)}
            badAt={(j) => bad(`${planKey}/${j}`)} onChange={(list) => set((l) => l.splice(0, l.length, ...list))}
            render={(p) => p.name || "—"} />
        ) : <p className="empty-note">{t("noPlans")}</p>}
        {undoNote}
      </aside>
      <section data-path={i >= 0 ? `${planKey}/${i}` : undefined}>
        {i === -1 && lead ? <><PlanUsers planKey={planKey} id={lead.id} />{lead.body}</> : plans[i] && (
          <>
            <div className="bar">
              <Field label={t("name")} path={`${planKey}/${i}/name`}>
                <input value={plans[i].name} onChange={(e) => set((l) => { l[i].name = e.target.value; })} />
              </Field>
              <span className="spacer" />
              <button type="button" className="subtle danger" onClick={remove}>
                <Icon glyph={GLYPHS.remove} />{t("remove")}
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
/** A lane of more packs than this shows two rows until opened. */
const FOLD_AT = 30;
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
  const [drag, setDrag] = useState<string | null>(null);
  const [open, setOpen] = useState<number[]>([]); // the weights of the lanes opened past their fold
  const lanes = lanesOf(plan);
  const line = lineAt(lanes, plan.threshold);
  const extra = Object.keys(plan.weights).filter((n) => !(n in data.packs)); // weighed, gone from the data file
  const shown = [...Object.keys(data.packs).filter((n) => onFloor(data.packs[n], difficulty, floor)), ...extra];
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
          onClick={() => toGap(line - 1)}><Icon glyph={GLYPHS.up} /></button>
        <button type="button" className="icon" aria-label={t("down")} title={t("down")} disabled={line + 1 > lanes.length}
          onClick={() => toGap(line + 1)}><Icon glyph={GLYPHS.down} /></button>
      </>}
    </div>
  );
  const gapOrLine = (g: number) => (g === line ? lineBar : <div className="gap" {...target(drag === LINE, lanes[g - 1])} />);
  const chips = <T extends string | number>(values: T[], value: T, label: (v: T) => string, pick: (v: T) => void) =>
    values.map((v) => (
      <button type="button" key={String(v)} className="chip" aria-pressed={v === value} onClick={() => pick(v)}>{label(v)}</button>
    ));
  return (<>
    <Row label={t("packs.eventPacks")} path={path ? `${path}/event_packs` : undefined} note={t("packs.eventPacksNote")}
      control={onChange
        ? <Select value={plan.event_packs} options={EVENT_MODES} label={(v) => tv("event_packs", v)} onChange={(v) => set({ event_packs: v })} />
        : <span>{tv("event_packs", plan.event_packs)}</span>} />
    <div className="packbar">
      {chips<PackMode>(["", "normal", "hard", "infinity", "extreme"], difficulty,
        (v) => (v ? t(BADGES[MODE_KEYS[v]][0]) : t("packs.anyDifficulty")) /* a badge's name: 普通, not NORMAL, in Chinese */, setDifficulty)}
      <span className="gap" />
      {chips(FLOORS, floor, (v) => (v ? t("packs.floor").replace("{n}", String(v)) : t("packs.anyFloor")), setFloor)}
      <span className="spacer" />
      {chips([false, true].map(String), String(images), (v) => t(v === "true" ? "packs.images" : "packs.names"), (v) => setImages(v === "true"))}
    </div>
    {onChange && <Note text={t("packs.hint")} block />}
    <p className="muted floorkey">
      {Object.values(BADGES).map(([key, cls]) => <small key={key} className={"fl" + cls}>{t(key)}</small>)}{t("packs.floorsKey")}
    </p>
    <div className={"lanes" + (images ? " images" : "") + (drag === LINE ? " moving" : "")}>
      {line === 0 && lineBar}
      {lanes.map((w, i) => {
        const here = shown.filter((n) => weightOf(plan, n) === w);
        // A lane of many packs (the unweighted ones, mostly) shows two rows until opened, so the weighted lanes and the line
        // stay near the top; a drag opens it, so every pack is a place to drop.
        const fold = here.length > FOLD_AT && !open.includes(w) && drag === null;
        return (
        <Fragment key={w}>
          {i > 0 && gapOrLine(i)}
          <div className={"lane" + (fold ? " folded" : "")} {...target(drag !== LINE, w)}>
            <span className={"w" + (w > 0 ? " pos" : w < 0 ? " neg" : "")}>{w > 0 ? `+${w}` : w}</span>
            <div className="packs">
              {here.map(chip)}
              {w === plan.unlisted && (
                <span className={"pk unlisted" + (path && bad(`${path}/unlisted`) ? " bad" : "")} data-path={path && `${path}/unlisted`}
                  {...dragged(UNLISTED)} {...clickable(UNLISTED)}>
                  {images && <span className="img" aria-hidden />}
                  <span className="nm">{t("packs.unlisted")}</span>
                  {typingOn(UNLISTED) && box(UNLISTED, plan.unlisted)}
                </span>
              )}
            </div>
            {here.length > FOLD_AT && drag === null && (
              <button type="button" className="more lane-more" aria-expanded={!fold}
                onClick={() => setOpen(fold ? [...open, w] : open.filter((x) => x !== w))}>
                {fold ? fill(t("packs.showAll"), { n: here.length }) : t("less")}
              </button>
            )}
          </div>
        </Fragment>
        );
      })}
      {gapOrLine(lanes.length)}
      {onChange && (
        <div className="lane add" {...target(drag !== null && drag !== LINE, null)}>
          {typing?.lane
            ? <>＋ {typing.what === UNLISTED ? t("packs.unlisted") : typing.what} {box(typing.what)}</>
            : <>＋ {t("packs.newLane")}</>}
        </div>
      )}
    </div>
  </>);
}
