// Named plans (spec 04 sections 6–8): the list of a kind's plans and the selected one's editor, which each plan kind's tab
// fills in (Deployment.tsx, Starlight.tsx, ThemePacks.tsx).
import type { ReactNode } from "react";
import { fill } from "./i18n";
import { freeName, newId, type Team } from "./model";
import { Field, Input, ReorderList, useEditor, usePick, useUndo, type PlanKey } from "./ui";

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
export function PlanTab<P extends { id: string; name: string }>({ planKey, tab, make, editor, lead }: {
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
