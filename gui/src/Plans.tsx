// Named plans (spec 04 sections 6–8) and the editors teams reuse for their custom values.
import { Fragment, useEffect, useState, type DragEvent, type KeyboardEvent, type ReactNode } from "react";
import { loadThemePacks } from "./api";
import {
  EVENT_MODES, GRACES, LEVELS, SINNERS, buyOrder, clickCard, clickEnhance, defaultStarlight, enhanceAll, floorLabel, freeName,
  gracePrice,
  lanesOf, lineAt, newId, newPackPlan, onFloor, parseThemePacks, selectAll, starlightCost, toggleSinner, weightOf,
  type DeploymentPlan, type Order, type PackPlanValues, type StarlightPlan, type StarlightValues, type ThemePackPlan,
  type ThemePacks,
} from "./model";
import { Field, ReorderList, Select, useEditor } from "./ui";

/** The 12 sinners in the game's grid; clicking adds one at the end of the order or leaves it out
 * (spec 04 section 6). Read-only without onChange. */
export function SinnerGrid({ order, onChange, path }: { order: Order; onChange?: (o: Order) => void; path: string }) {
  const { t, bad } = useEditor();
  return (<>
    {onChange && <p className="muted">{t("order.hint")}</p>}
    <div className={"sinners" + (bad(path) ? " bad" : "")}>
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
    <>{onChange && <p className="muted">{t("starlight.hint")}</p>}
    <div className={"starlight" + (onChange ? "" : " readonly")}>
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
          <span className="muted">{t("starlight.enhanceAll")}</span>
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

type PlanKey = "deployment_order_plans" | "starlight_plans" | "theme_pack_plans";

/** A list of named plans on the left, the selected plan's editor on the right. */
function PlanTab<P extends { id: string; name: string }>({ planKey, tab, make, editor, lead }: {
  planKey: PlanKey; tab: "tab.deployment" | "tab.starlight" | "tab.themepacks"; make: () => Omit<P, "id" | "name">;
  editor: (plan: P, change: (p: P) => void, path: string) => ReactNode;
  lead?: { label: string; body: ReactNode };
}) {
  const { s, update, t, bad } = useEditor();
  const plans = s[planKey] as unknown as P[];
  const [sel, setSel] = useState(lead ? -1 : 0);
  const i = Math.min(sel, plans.length - 1);
  const set = (fn: (list: P[]) => void) => update((d) => fn(d[planKey] as unknown as P[]));
  const add = () => {
    set((list) => list.push({ ...make(), id: newId(), name: freeName(t(tab), plans.map((p) => p.name)) } as P));
    setSel(plans.length);
  };
  return (
    <div className="split">
      <aside>
        {lead && <button type="button" className={"lead" + (i === -1 ? " selected" : "")} onClick={() => setSel(-1)}>{lead.label}</button>}
        {plans.length || lead ? (
          <ReorderList items={plans} keyOf={(p) => p.id} selected={i} onSelect={setSel}
            badAt={(j) => bad(`${planKey}/${j}`)} onChange={(list) => set((l) => l.splice(0, l.length, ...list))}
            render={(p) => p.name || "—"} />
        ) : <p className="muted">{t("noPlans")}</p>}
        <button type="button" onClick={add}>+ {t("add")}</button>
      </aside>
      <section>
        {i === -1 && lead ? lead.body : plans[i] && (
          <>
            <div className="row">
              <Field label={t("name")} path={`${planKey}/${i}/name`}>
                <input value={plans[i].name} onChange={(e) => set((l) => { l[i].name = e.target.value; })} />
              </Field>
              <button type="button" className="danger" onClick={() => { set((l) => l.splice(i, 1)); setSel(Math.max(0, i - 1)); }}>
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
      lead={{ label: t("defaultPlanLocked"), body: <>
        <p className="muted">{t("defaultPlanNote")}</p>{note}
        <PackPlanEditor data={data} plan={data.default_plan} path="" />
      </> }}
      editor={(p, change, path) => <>
        {note}
        <PackPlanEditor data={data} plan={p} path={path} onChange={(v) => change({ ...p, ...v })} />
      </>} />
  );
}

// #241's covers (theme_pack_covers/index.json: pack name -> file), bundled at build time; a pack without one, or a
// build before they exist, shows a blank card. The name always shows: some packs share one cover (1201/1203/1205).
const COVERS_DIR = "../../assets/resource/base/data/theme_pack_covers/";
const COVER_URLS = import.meta.glob<string>("../../assets/resource/base/data/theme_pack_covers/*.webp",
  { eager: true, query: "?url", import: "default" });
const COVER_INDEX = Object.values(import.meta.glob<Record<string, string>>("../../assets/resource/base/data/theme_pack_covers/index.json",
  { eager: true, import: "default" }))[0] ?? {};
const coverOf = (name: string): string | undefined => COVER_URLS[COVERS_DIR + COVER_INDEX[name]];

const UNLISTED = "\u0000unlisted"; // what the "unlisted packs" chip drags: no pack name starts with NUL
const LINE = "\u0000line";

/** Design A of #240: one lane per weight in use (0 always), highest first, and the threshold line between lanes.
 * Drag a pack to another lane, or onto + for a new weight; click one to type its weight. Read-only without onChange. */
function PackPlanEditor({ data, plan, path, onChange }: {
  data: ThemePacks; plan: PackPlanValues; path: string; onChange?: (p: PackPlanValues) => void;
}) {
  const { t, tv, bad } = useEditor();
  const [difficulty, setDifficulty] = useState<"" | "normal" | "hard">("");
  const [floor, setFloor] = useState(0);
  const [images, setImages] = useState(false);
  const [drag, setDrag] = useState<string | null>(null);
  const floorText = { normal: t("packs.floorsNormal"), hard: t("packs.floorsHard"), sep: t("packs.floorSep"), join: " · " };
  const lanes = lanesOf(plan);
  const line = lineAt(lanes, plan.threshold);
  const extra = Object.keys(plan.weights).filter((n) => !(n in data.packs)); // weighed, gone from the data file
  const shown = [...Object.keys(data.packs).filter((n) => onFloor(data.packs[n], difficulty, floor)), ...extra];
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
    const floors = data.packs[name] === undefined ? undefined : floorLabel(data.packs[name], floorText);
    return (
      <span key={name} className={"pk" + (path && bad(`${path}/weights/${name}`) ? " bad" : "")}
        {...dragged(name)} {...clickable(name, weightOf(plan, name))}>
        {images && (coverOf(name) ? <img className="img" src={coverOf(name)} alt="" draggable={false} /> : <span className="img" aria-hidden />)}
        <span className="nm">{name}</span>
        <small>{floors ?? <em>{t("packNotInData")}</em>}</small>
      </span>
    );
  };
  const lineBar = (
    <div className={"thr" + (path && bad(`${path}/threshold`) ? " bad" : "")} {...dragged(LINE)}>
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
  const chips = <T extends string | number>(values: T[], value: T, label: (v: T) => string, pick: (v: T) => void) =>
    values.map((v) => (
      <button type="button" key={String(v)} className="chip" aria-pressed={v === value} onClick={() => pick(v)}>{label(v)}</button>
    ));
  return (<>
    <div className="packbar">
      {chips<"" | "normal" | "hard">(["", "normal", "hard"], difficulty, (v) => (v ? v.toUpperCase() : t("packs.anyDifficulty")), setDifficulty)}
      <span className="gap" />
      {chips([0, 1, 2, 3, 4, 5], floor, (v) => (v ? t("packs.floor").replace("{n}", String(v)) : t("packs.anyFloor")), setFloor)}
      <span className="spacer" />
      {chips([false, true].map(String), String(images), (v) => t(v === "true" ? "packs.images" : "packs.names"), (v) => setImages(v === "true"))}
    </div>
    {onChange && <p className="muted">{t("packs.hint")}</p>}
    <div className={"lanes" + (images ? " images" : "") + (drag === LINE ? " moving" : "")}>
      {line === 0 && lineBar}
      {lanes.map((w, i) => (
        <Fragment key={w}>
          {i > 0 && gapOrLine(i)}
          <div className="lane" {...target(drag !== LINE, w)}>
            <span className={"w" + (w > 0 ? " pos" : w < 0 ? " neg" : "")}>{w > 0 ? `+${w}` : w}</span>
            <div className="packs">
              {shown.filter((n) => weightOf(plan, n) === w).map(chip)}
              {w === plan.unlisted && (
                <span className={"pk unlisted" + (path && bad(`${path}/unlisted`) ? " bad" : "")}
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
    <Field label={t("packs.eventPacks")} path={path && `${path}/event_packs`} note={t("packs.eventPacksNote")}>
      {onChange
        ? <Select value={plan.event_packs} options={EVENT_MODES} label={(v) => tv("event_packs", v)} onChange={(v) => set({ event_packs: v })} />
        : <span>{tv("event_packs", plan.event_packs)}</span>}
    </Field>
  </>);
}
