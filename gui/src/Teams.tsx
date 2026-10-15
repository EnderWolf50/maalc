// Teams (spec 04 section 9): list order is rotation order.
import { useState } from "react";
import { resetTeamTimes } from "./api";
import { BOOSTS, KEYWORDS, SINNERS, defaultStarlight, freeName, newId, newTeam, teamEnum, type Team } from "./model";
import { OrderEditor, StarlightEditor } from "./Plans";
import { Field, Num, ReorderList, Select, useEditor } from "./ui";

export function TeamsTab() {
  const { s, update, t, bad } = useEditor();
  const [sel, setSel] = useState(0);
  const i = Math.min(sel, s.teams.length - 1);
  return (
    <div className="split">
      <aside>
        {s.teams.length ? (
          <ReorderList items={s.teams} keyOf={(x) => x.id} selected={i} onSelect={setSel} badAt={(j) => bad(`teams/${j}`)}
            onChange={(teams) => update((d) => { d.teams = teams; })}
            render={(x) => (
              <span className={x.enabled ? "" : "muted"}>{x.name || "—"} <small>#{x.game_team}</small></span>
            )} />
        ) : <p className={"muted" + (bad("teams") ? " bad" : "")}>{t("noTeams")}</p>}
        <button type="button" onClick={() => {
          const n = s.teams.length + 1;
          update((d) => { d.teams.push(newTeam(n, `${t("teamName")} ${n}`)); });
          setSel(n - 1);
        }}>+ {t("add")}</button>
      </aside>
      <section>{s.teams[i] && <TeamEditor i={i} onRemove={() => setSel(Math.max(0, i - 1))} />}</section>
    </div>
  );
}

function TeamEditor({ i, onRemove }: { i: number; onRemove: () => void }) {
  const { s, update, t, tv, bad } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  const pick = (field: "usage" | "heal" | "trial_risk_weight") => (
    <Field label={t(`team.${field}`)} path={`${path}/${field}`}>
      <Select value={team[field]} options={teamEnum(field)} label={(v) => tv(field, v)} onChange={(v) => set({ [field]: v })} />
    </Field>
  );
  const [notice, setNotice] = useState("");

  // "plan id" or "" for custom. Switching to custom copies the plan's values (spec 04 section 9).
  const orderSource = "plan" in team.deployment_order ? team.deployment_order.plan : "";
  const order = "custom" in team.deployment_order ? team.deployment_order.custom
    : s.deployment_order_plans.find((p) => p.id === orderSource)?.order;
  const starSource = "plan" in team.starlight ? team.starlight.plan : "";
  const starPlan = s.starlight_plans.find((p) => p.id === starSource);
  const star = "custom" in team.starlight ? team.starlight.custom : starPlan;

  const saveOrderPlan = () => update((d) => {
    const id = newId();
    d.deployment_order_plans.push({ id, name: freeName(`${team.name} ${t("planSuffixDeploy")}`, d.deployment_order_plans.map((p) => p.name)), order: [...order!] });
    d.teams[i].deployment_order = { plan: id };
  });
  const saveStarPlan = () => update((d) => {
    const id = newId();
    const { levels, priority, convert_leftover } = star!;
    d.starlight_plans.push({ id, name: freeName(`${team.name} ${t("planSuffixStarlight")}`, d.starlight_plans.map((p) => p.name)), levels: [...levels], priority: [...priority], convert_leftover });
    d.teams[i].starlight = { plan: id };
  });

  return (
    <div className="team">
      <div className="row">
        <Field label={t("name")} path={`${path}/name`}>
          <input value={team.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <label className="check"><input type="checkbox" checked={team.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("team.enabled")}</label>
        <button type="button" onClick={async () => {
          if (!confirm(t("resetConfirm"))) return;
          try { await resetTeamTimes(team.id); setNotice(t("resetDone")); } catch (e) { setNotice(String(e)); }
        }}>{t("resetTimes")}</button>
        <button type="button" className="danger" onClick={() => { update((d) => { d.teams.splice(i, 1); }); onRemove(); }}>{t("remove")}</button>
      </div>
      {notice && <p className="notice">{notice}</p>}

      <div className="grid">
        <Field label={t("team.game_team")} path={`${path}/game_team`}>
          <Num value={team.game_team} min={1} max={40} onChange={(v) => set({ game_team: v })} />
        </Field>
        <Field label={t("team.keyword")} path={`${path}/keyword`}>
          <Select value={team.keyword} options={KEYWORDS} onChange={(v) => set({ keyword: v })} />
        </Field>
        {pick("usage")}
        <Field label={t("team.hard_from_floor")} path={`${path}/hard_from_floor`}>
          <Num value={team.hard_from_floor} min={0} max={5} onChange={(v) => set({ hard_from_floor: v })} />
        </Field>
        <Field label={t("team.theme_pack_plan")} path={`${path}/theme_pack_plan`}>
          <select value={team.theme_pack_plan} onChange={(e) => set({ theme_pack_plan: e.target.value })}>
            <option value="default">{t("defaultPlan")}</option>
            {s.theme_pack_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {missing(team.theme_pack_plan !== "default" && team.theme_pack_plan, s.theme_pack_plans)}
          </select>
        </Field>
        {pick("trial_risk_weight")}
        <Field label={t("team.shop_refresh_limit")} path={`${path}/shop_refresh_limit`}>
          <Num value={team.shop_refresh_limit} min={0} onChange={(v) => set({ shop_refresh_limit: v })} />
        </Field>
        {pick("heal")}
        <Field label={t("team.reserve_cost")} path={`${path}/reserve_cost`}>
          <Num value={team.reserve_cost} min={0} onChange={(v) => set({ reserve_cost: v })} />
        </Field>
        <Field label={t("team.min_alive")} path={`${path}/min_alive`} note={t("team.min_alive_note")}>
          <Num value={team.min_alive} min={0} max={12} onChange={(v) => set({ min_alive: v })} />
        </Field>
        <Field label={t("team.guard_turns")} path={`${path}/guard_turns`} note={t("team.guard_turns_note")}>
          <Num value={team.guard_turns} min={0} max={5} onChange={(v) => set({ guard_turns: v })} />
        </Field>
      </div>

      <div className="columns">
        <fieldset>
          <legend>{t("team.deployment_order")}</legend>
          <Field label="" path={`${path}/deployment_order`}>
            <select value={orderSource} onChange={(e) => set({
              deployment_order: e.target.value ? { plan: e.target.value } : { custom: [...(order ?? SINNERS)] },
            })}>
              <option value="">{t("custom")}</option>
              {s.deployment_order_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              {missing(orderSource, s.deployment_order_plans)}
            </select>
          </Field>
          {"custom" in team.deployment_order ? (
            <>
              <button type="button" onClick={saveOrderPlan}>{t("saveAsPlan")}</button>
              <OrderEditor order={team.deployment_order.custom} path={`${path}/deployment_order/custom`}
                onChange={(custom) => set({ deployment_order: { custom } })} />
            </>
          ) : order && <ol className="preview">{order.map((x) => <li key={x}>{x}</li>)}</ol>}
        </fieldset>

        <fieldset>
          <legend>{t("team.reward_cards")}</legend>
          <div className={bad(`${path}/reward_cards`) ? "bad" : ""}>
            <ReorderList items={team.reward_cards} keyOf={(x) => x} onChange={(reward_cards) => set({ reward_cards })}
              render={(x, j) => <>{j + 1}. {x}</>} />
          </div>
        </fieldset>
      </div>

      <fieldset>
        <legend>{t("team.starlight")}</legend>
        <Field label="" path={`${path}/starlight`}>
          <select value={starSource} onChange={(e) => {
            const plan = s.starlight_plans.find((p) => p.id === starSource);
            set({
              starlight: e.target.value ? { plan: e.target.value } : {
                custom: plan ? { levels: [...plan.levels], priority: [...plan.priority], convert_leftover: plan.convert_leftover } : defaultStarlight(),
              },
            });
          }}>
            <option value="">{t("custom")}</option>
            {s.starlight_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {missing(starSource, s.starlight_plans)}
          </select>
        </Field>
        {"custom" in team.starlight ? (
          <>
            <button type="button" onClick={saveStarPlan}>{t("saveAsPlan")}</button>
            <StarlightEditor value={team.starlight.custom} path={`${path}/starlight/custom`}
              onChange={(custom) => set({ starlight: { custom } })} />
          </>
        ) : starPlan && (
          <p className="muted">{starPlan.priority.filter((n) => starPlan.levels[n - 1] !== "none")
            .map((n) => `${BOOSTS[n - 1]} ${tv("level", starPlan.levels[n - 1])}`).join(" → ") || tv("level", "none")}</p>
        )}
      </fieldset>
    </div>
  );
}

/** Keep a dangling plan id selectable so the select shows it instead of silently changing it. */
function missing(id: string | false, plans: { id: string }[]) {
  return id && !plans.some((p) => p.id === id) ? <option value={id}>? {id}</option> : null;
}
