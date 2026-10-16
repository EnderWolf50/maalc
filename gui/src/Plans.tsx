// Named plans (spec 04 sections 6–8) and the editors teams reuse for their custom values.
import { useEffect, useState, type ReactNode } from "react";
import { loadThemePacks } from "./api";
import {
  BOOSTS, BOOST_COST, LEVELS, MARKS, SINNERS, clickLevel, defaultStarlight, freeName, lowestLevel, newId, starlightCost,
  toggleSinner,
  type DeploymentPlan, type Order, type StarlightPlan, type StarlightValues, type ThemePackPlan, type ThemePacks,
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

/** Base, + and ++ as one control, like the game's starlight card; clicking a lit segment turns it and above off. */
function LevelSelector({ label, title, cost, level, onChange }: {
  label: string; title?: string; cost: number; level: string; onChange: (level: string) => void;
}) {
  const lit = LEVELS.indexOf(level);
  return (
    <div className="levels" title={title}>
      {[label, "+", "++"].map((text, seg) => (
        <button type="button" key={seg} className={seg < lit ? "lit" : ""} aria-pressed={seg < lit}
          onClick={() => onChange(clickLevel(level, seg))}>
          {seg === 0 && <small>{cost * Math.max(1, lit)}</small>}{text}
        </button>
      ))}
    </div>
  );
}

export function StarlightEditor({ value, onChange, path }: {
  value: StarlightValues; onChange: (v: StarlightValues) => void; path: string;
}) {
  const { t, bad } = useEditor();
  const setLevels = (levels: string[]) => onChange({ ...value, levels });
  return (
    <div className="starlight">
      <div className={"boosts" + (bad(`${path}/levels`) ? " bad" : "")}>
        <div className="boost-tools">
          <LevelSelector label={t("starlight.all")} cost={BOOST_COST.reduce((a, b) => a + b)} level={lowestLevel(value.levels)}
            onChange={(l) => setLevels(value.levels.map(() => l))} />
          <button type="button" onClick={() => setLevels(value.levels.map(() => "none"))}>{t("starlight.clear")}</button>
          <span className="total">{t("starlight.total")} <b>{starlightCost(value.levels)}</b></span>
        </div>
        {BOOSTS.map((b, i) => (
          <LevelSelector key={b} label={`${i + 1}. ${b}`} title={b} cost={BOOST_COST[i]} level={value.levels[i]}
            onChange={(l) => setLevels(value.levels.map((x, j) => (j === i ? l : x)))} />
        ))}
      </div>
      <div>
        <h4 className={bad(`${path}/priority`) ? "bad" : ""}>{t("starlight.priority")}</h4>
        <ReorderList items={value.priority} keyOf={String} onChange={(priority) => onChange({ ...value, priority })}
          render={(n, i) => <>{i + 1}. {BOOSTS[n - 1] ?? n}</>} />
        <label className="check">
          <input type="checkbox" checked={value.convert_leftover}
            onChange={(e) => onChange({ ...value, convert_leftover: e.target.checked })} />
          {t("starlight.convert_leftover")}
        </label>
      </div>
    </div>
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
  const [data, setData] = useState<ThemePacks>({ packs: [], default_plan: {} });
  const [error, setError] = useState("");
  useEffect(() => { loadThemePacks().then(setData, (e) => setError(String(e))); }, []);
  const note = error && <p className="bad">{t("themePacksError")}: {error}</p>;
  return (
    <PlanTab<ThemePackPlan> planKey="theme_pack_plans" tab="tab.themepacks" make={() => ({ marks: {} })}
      lead={{ label: t("defaultPlanLocked"), body: <>
        <p className="muted">{t("defaultPlanNote")}</p>{note}
        <MarksTable packs={data.packs} marks={data.default_plan} path="" />
      </> }}
      editor={(p, change, path) => <>
        <p className="muted">{t("marksNote")}</p>{note}
        <MarksTable packs={data.packs} marks={p.marks} path={`${path}/marks`} onChange={(marks) => change({ ...p, marks })} />
      </>} />
  );
}

/** Every pack of the season, then marked packs the data file no longer lists. Read-only without onChange. */
function MarksTable({ packs, marks, path, onChange }: {
  packs: string[]; marks: Record<string, string>; path: string; onChange?: (marks: Record<string, string>) => void;
}) {
  const { t, tv, bad } = useEditor();
  const rows = [...packs, ...Object.keys(marks).filter((name) => !packs.includes(name))];
  const set = (name: string, mark: string) => {
    const next = { ...marks, [name]: mark };
    if (mark === "neutral") delete next[name]; // unlisted packs are neutral (spec 04 section 8)
    onChange?.(next);
  };
  return (
    <table>
      <tbody>
        {rows.map((name) => (
          <tr key={name} className={path && bad(`${path}/${name}`) ? "bad" : ""}>
            <td>{name}{!packs.includes(name) && <em className="tag">{t("packNotInData")}</em>}</td>
            <td>
              {onChange
                ? <Select value={marks[name] ?? "neutral"} options={MARKS} label={(v) => tv("mark", v)} onChange={(v) => set(name, v)} />
                : tv("mark", marks[name] ?? "neutral")}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
