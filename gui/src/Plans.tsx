// Named plans (spec 04 sections 6–8) and the editors teams reuse for their custom values.
import { useEffect, useState, type ReactNode } from "react";
import { loadThemePacks } from "./api";
import {
  GRACES, LEVELS, MARKS, SINNERS, buyOrder, clickCard, clickEnhance, defaultStarlight, enhanceAll, freeName, gracePrice,
  newId, selectAll, starlightCost, toggleSinner,
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
