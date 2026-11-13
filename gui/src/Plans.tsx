// Named plans (spec 04 sections 6–8) and the editors teams reuse for their custom values.
import { Fragment, useEffect, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { loadThemePacks } from "./api";
import {
  EVENT_MODES, GRACES, LEVELS, SINNERS, buyOrder, byFirstFloor, clickCard, graceName, clickEnhance, defaultStarlight, enhanceAll, floorBadges, freeName,
  gracePrice,
  lanesOf, lineAt, newId, newPackPlan, onFloor, parseThemePacks, selectAll, starlightCost, toggleSinner, weightOf,
  type DeploymentPlan, type Order, type PackMode, type PackPlanValues, type StarlightPlan, type StarlightValues, type ThemePackPlan,
  type ThemePacks,
} from "./model";
import { GIFT_BY_ID, giftName } from "./giftCatalog";
import { listsOfPlan, packWanted } from "./gifts";
import { fill } from "./i18n";
import { Field, Icon, ReorderList, Select, useEditor, usePick, withBreaks, type PlanKey } from "./ui";

/** The 12 sinners in the game's grid; clicking adds one at the end of the order or leaves it out
 * (spec 04 section 6). Read-only without onChange. */
export function SinnerGrid({ order, onChange, path }: { order: Order; onChange?: (o: Order) => void; path: string }) {
  const { t, bad } = useEditor();
  return (<>
    {onChange && <p className="muted">{t("order.hint")}</p>}
    <div className={"sinners" + (bad(path) ? " bad" : "") + (onChange ? "" : " readonly")} data-path={path}>
      {SINNERS.map((s) => {
        const n = order.indexOf(s) + 1;
        const kind = n === 0 ? "" : n <= 7 ? "deployed" : "backup";
        return (
          <button type="button" key={s} className={"sinner " + kind} aria-disabled={onChange ? undefined : true} aria-pressed={n > 0}
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
    <>{onChange && <p className="muted">{t("starlight.hint")}</p>}
    <div className={"starlight" + (onChange ? "" : " readonly")} data-path={path}>
      <div className={"graces" + (bad(`${path}/levels`) || bad(`${path}/priority`) ? " bad" : "")}>
        {GRACES.map((g, i) => {
          const n = i + 1;
          const level = value.levels[i];
          const rank = order.indexOf(n) + 1;
          const effects = g.effects[level as "plus" | "plus2"] ?? g.effects.base;
          return (
            <div key={g.en} className={`grace ${level}`} role="group" aria-label={graceName(g, zh)} title={`${n}. ${g.en} (${tv("level", level)})`}>
              {/* The whole card is its select button; + and ++ sit above it. */}
              <button type="button" className="pick" aria-pressed={rank > 0} disabled={!onChange}
                aria-label={`${graceName(g, zh)} ★ ${gracePrice(n, level === "none" ? "base" : level)}`}
                onClick={() => set((v) => clickCard(v, n))} />
              {rank > 0 && <span className="rank">{rank}</span>}
              <span className="price">★ {gracePrice(n, level === "none" ? "base" : level)}</span>
              <span className="name">{graceName(g, zh)}{zh && g.zh && <small>{g.en}</small>}</span>
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
          <span className="muted">{t("starlight.enhanceAll")}</span>
          <button type="button" aria-label={`${t("starlight.enhanceAll")} +`} onClick={() => set((v) => enhanceAll(v, 1))}>+</button>
          <button type="button" aria-label={`${t("starlight.enhanceAll")} ++`} onClick={() => set((v) => enhanceAll(v, 2))}>++</button>
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

/** A list of named plans on the left, the selected plan's editor on the right; `lead`, a read-only plan above the list. */
function PlanTab<P extends { id: string; name: string }>({ planKey, tab, make, editor, lead }: {
  planKey: PlanKey; tab: "tab.deployment" | "tab.starlight" | "tab.themepacks"; make: () => Omit<P, "id" | "name">;
  editor: (plan: P, change: (p: P) => void, path: string) => ReactNode;
  lead?: { id: string; label: string; body: ReactNode };
}) {
  const { s, update, t, bad } = useEditor();
  const plans = s[planKey] as unknown as P[];
  const [i, setSel] = usePick(planKey, plans, lead?.id); // -1: the lead
  const set = (fn: (list: P[]) => void) => update((d) => fn(d[planKey] as unknown as P[]));
  const add = () => {
    const id = newId();
    set((list) => list.push({ ...make(), id, name: freeName(t(tab), plans.map((p) => p.name)) } as P));
    setSel(id);
  };
  return (
    <div className="split">
      <aside>
        {lead && <button type="button" className={"lead" + (i === -1 ? " selected" : "")} onClick={() => setSel(lead.id)}><Icon name="lock" />{lead.label}</button>}
        {plans.length || lead ? (
          <ReorderList items={plans} keyOf={(p) => p.id} nameOf={(p) => p.name || "—"} selected={i} onSelect={(j, list) => setSel(list[j].id)}
            badAt={(j) => bad(`${planKey}/${j}`)} onChange={(list) => set((l) => l.splice(0, l.length, ...list))}
            render={(p) => p.name || "—"} />
        ) : <p className="muted">{t("noPlans")}</p>}
        <button type="button" onClick={add}>+ {t("add")}</button>
      </aside>
      <section data-path={i >= 0 ? `${planKey}/${i}` : undefined}>
        {i === -1 && lead ? lead.body : plans[i] && (
          <>
            <div className="row">
              <Field label={t("name")} path={`${planKey}/${i}/name`}>
                <input value={plans[i].name} onChange={(e) => set((l) => { l[i].name = e.target.value; })} />
              </Field>
              <button type="button" className="danger" onClick={() => { set((l) => l.splice(i, 1)); setSel((plans[i - 1] ?? plans[i + 1])?.id); }}>
                {t("remove")}
              </button>
            </div>
            {editor(plans[i], (p) => set((l) => { l[i] = p; }), `${planKey}/${i}`)}
          </>
        )}
      </section>
    </div>
  );
}

export const DeploymentTab = () => (
  <PlanTab<DeploymentPlan> planKey="deployment_order_plans" tab="tab.deployment" make={() => ({ order: [...SINNERS] })}
    editor={(p, change, path) => (
      <div className="plan-card"><SinnerGrid order={p.order} path={`${path}/order`} onChange={(order) => change({ ...p, order })} /></div>
    )} />
);

export const StarlightTab = () => (
  <PlanTab<StarlightPlan> planKey="starlight_plans" tab="tab.starlight" make={defaultStarlight}
    editor={(p, change, path) => (
      <div className="plan-card"><StarlightEditor value={p} path={path} onChange={(v) => change({ ...p, ...v })} /></div>
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
  const [query, setQuery] = useState("");
  const [drag, setDrag] = useState<string | null>(null);
  const lanes = lanesOf(plan);
  const line = lineAt(lanes, plan.threshold);
  const extra = Object.keys(plan.weights).filter((n) => !(n in data.packs)); // weighed, gone from the data file
  const q = query.trim().toLowerCase();
  const shown = [...Object.keys(data.packs).filter((n) => onFloor(data.packs[n], difficulty, floor)), ...extra]
    .filter((n) => !q || n.toLowerCase().includes(q));
  const set = (patch: Partial<PackPlanValues>) => onChange?.({ ...plan, ...patch });
  const weigh = (what: string, w: number) => (what === UNLISTED ? set({ unlisted: w }) : set({ weights: { ...plan.weights, [what]: w } }));
  const ask = (what: string, current?: number) => {
    const text = prompt(t("packs.weightPrompt"), current === undefined ? "" : String(current));
    if (text === null || text.trim() === "") return;
    const w = Number(text);
    if (Number.isInteger(w) && w >= -10 && w <= 10) weigh(what, w);
    else alert(t("packs.weightRange"));
  };
  const dropOn = (w: number | null) => (e: DragEvent) => {
    e.preventDefault();
    if (drag === LINE && w !== null) set({ threshold: w });
    else if (drag && drag !== LINE) (w === null ? ask(drag) : weigh(drag, w));
    setDrag(null);
  };
  const target = (accepts: boolean, w: number | null) => (onChange && accepts
    ? { onDragOver: (e: DragEvent) => e.preventDefault(), onDrop: dropOn(w) } : {});
  const dragged = (what: string) => (onChange ? {
    draggable: true,
    onDragStart: (e: DragEvent) => { setDrag(what); e.dataTransfer.effectAllowed = "move"; e.dataTransfer.setData("text/plain", what); },
    onDragEnd: () => setDrag(null),
  } : {});
  const clickable = (what: string, current: number) => (onChange ? {
    role: "button", tabIndex: 0, onClick: () => ask(what, current),
    onKeyDown: (e: KeyboardEvent) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); ask(what, current); } },
  } : {});
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
        {...dragged(name)} {...clickable(name, weightOf(plan, name))} title={cover ? name : undefined}>
        {cover ? <img className="img" src={cover} alt={name} draggable={false} /> : images && <span className="img" aria-hidden />}
        {!cover && <span className="nm">{name}</span>}
        {floors
          ? floors.map((f) => {
            const label = `${t(BADGES[f.mode][0])} ${f.text}`;
            return <small key={f.mode} className={"fl" + BADGES[f.mode][1]} role="img" title={label} aria-label={label}>{f.text}</small>;
          })
          : <small><em>{t("packNotInData")}</em></small>}
        {wanted.length > 0 && <small className="wk" role="img" title={wantedTip} aria-label={wantedTip}>{t("packs.wanted")}</small>}
      </span>
    );
  };
  const lineLabel = fill(t("packs.threshold"), { n: plan.threshold });
  const lineBar = (
    <div className={"thr" + (path && bad(`${path}/threshold`) ? " bad" : "")} data-path={path && `${path}/threshold`} {...dragged(LINE)}>
      <span>{lineLabel}</span>
      {onChange && <>
        <button type="button" className="icon" aria-label={`${t("up")} ${lineLabel}`} title={t("up")} disabled={line - 1 < 1}
          onClick={() => toGap(line - 1)}><Icon name="up" /></button>
        <button type="button" className="icon" aria-label={`${t("down")} ${lineLabel}`} title={t("down")} disabled={line + 1 > lanes.length}
          onClick={() => toGap(line + 1)}><Icon name="down" /></button>
      </>}
    </div>
  );
  const gapOrLine = (g: number) => (g === line ? lineBar : <div className="gap" {...target(drag === LINE, lanes[g - 1])} />);
  // A filter is one segmented control; `short` is what a chip shows when its name is long (the floor numbers).
  const chips = <T extends string | number>(values: T[], value: T, label: (v: T) => string, pick: (v: T) => void, short?: (v: T) => string) =>
    values.map((v) => (
      <button type="button" key={String(v)} className="chip" aria-pressed={v === value} aria-label={short && label(v)}
        title={short && label(v)} onClick={() => pick(v)}>{short ? short(v) : label(v)}</button>
    ));
  // The plan's one setting outside the lanes first; then the lanes with what filters them (the filters only change the view).
  return (<>
    <div className="rows">
      <Field label={t("packs.eventPacks")} path={path && `${path}/event_packs`} note={t("packs.eventPacksNote")}>
        {onChange
          ? <Select value={plan.event_packs} options={EVENT_MODES} label={(v) => tv("event_packs", v)} onChange={(v) => set({ event_packs: v })} />
          : <span>{tv("event_packs", plan.event_packs)}</span>}
      </Field>
    </div>
    <div className="pack-card">
    <div className="packbar">
      <span className="seg">
        {chips<PackMode>(["", "normal", "hard", "infinity", "extreme"], difficulty, (v) => (v ? v.toUpperCase() : t("packs.anyDifficulty")), setDifficulty)}
      </span>
      <span className="spacer" />
      {/* Names or cover images: a switch of the view, drawn as one segmented control, apart from the filters. */}
      <span className="seg">
        {chips([false, true].map(String), String(images), (v) => t(v === "true" ? "packs.images" : "packs.names"), (v) => setImages(v === "true"))}
      </span>
      <span className="break" />
      <span className="seg floors">
        {chips(FLOORS, floor, (v) => (v ? t("packs.floor").replace("{n}", String(v)) : t("packs.anyFloor")), setFloor,
          (v) => (v ? String(v) : t("packs.anyFloor")))}
      </span>
      <label className="search"><Icon name="search" />
        <input type="search" value={query} placeholder={t("packs.search")} aria-label={t("packs.search")} onChange={(e) => setQuery(e.target.value)} />
      </label>
      {/* The badges' key stays with the filters while the lanes scroll. */}
      <p className="muted floorkey">
        {Object.values(BADGES).map(([key, cls]) => <small key={key} className={"fl" + cls}>{t(key)}</small>)}{t("packs.floorsKey")}
      </p>
    </div>
    {onChange && <p className="muted">{withBreaks(t("packs.hint"))}</p>}
    <div className={"lanes" + (images ? " images" : "") + (drag === LINE ? " moving" : "")}>
      {line === 0 && lineBar}
      {lanes.map((w, i) => (
        <Fragment key={w}>
          {i > 0 && gapOrLine(i)}
          <div className="lane" {...target(drag !== LINE, w)}>
            <span className={"w" + (w > 0 ? " pos" : w < 0 ? " neg" : "")}>{w > 0 ? `+${w}` : w}</span>
            <div className="packs">
              {shown.filter((n) => weightOf(plan, n) === w).sort(byFirstFloor(data.packs)).map(chip)}
              {w === plan.unlisted && (
                <span className={"pk unlisted" + (path && bad(`${path}/unlisted`) ? " bad" : "")} data-path={path && `${path}/unlisted`}
                  {...dragged(UNLISTED)} {...clickable(UNLISTED, plan.unlisted)}>
                  {images && <span className="img" aria-hidden />}
                  <span className="nm">{t("packs.unlisted")}</span>
                </span>
              )}
            </div>
          </div>
        </Fragment>
      ))}
      {gapOrLine(lanes.length)}
      {onChange && <div className="lane add" {...target(drag !== null && drag !== LINE, null)}>＋ {t("packs.newLane")}</div>}
    </div>
    </div>
  </>);
}
