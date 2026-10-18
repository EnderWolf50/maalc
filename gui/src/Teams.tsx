// Teams (spec 04 section 9): list order is rotation order.
import { useState } from "react";
import { resetTeamTimes } from "./api";
import {
  KEYWORDS, MAX_GIFTS, SEARCH_GIFTS, SEARCH_TABS, SINNERS, defaultStarlight, freeName, newId, newTeam, teamEnum, toggleGift,
  type GiftRef, type SearchGift, type Team,
} from "./model";
import { SinnerGrid, StarlightEditor } from "./Plans";
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
  const pick = (field: "heal" | "trial_risk_weight") => (
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

  const planSelect = (value: string, plans: { id: string; name: string }[], onChange: (id: string) => void) => (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("custom")}</option>
      {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      {missing(value, plans)}
    </select>
  );

  // Laid out like AALC's team page: who and what on top, the sinner grid, starlight, then the rest.
  return (
    <div className="team">
      <div className="bar">
        <Field label={t("name")} path={`${path}/name`}>
          <input value={team.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label={t("team.game_team")} path={`${path}/game_team`}>
          <Num value={team.game_team} min={1} max={40} onChange={(v) => set({ game_team: v })} />
        </Field>
        <Field label={t("team.keyword")} path={`${path}/keyword`}>
          <Select value={team.keyword} options={KEYWORDS} onChange={(v) => set({ keyword: v })} />
        </Field>
        <label className="check"><input type="checkbox" checked={team.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("team.enabled")}</label>
        <span className="spacer" />
        <button type="button" onClick={async () => {
          if (!confirm(t("resetConfirm"))) return;
          try { await resetTeamTimes(team.id); setNotice(t("resetDone")); } catch (e) { setNotice(String(e)); }
        }}>{t("resetTimes")}</button>
        <button type="button" className="danger" onClick={() => { update((d) => { d.teams.splice(i, 1); }); onRemove(); }}>{t("remove")}</button>
      </div>
      {notice && <p className="notice">{notice}</p>}

      <fieldset>
        <legend>{t("team.deployment_order")}</legend>
        <div className={"row" + (bad(`${path}/deployment_order`) && !("custom" in team.deployment_order) ? " bad" : "")}>
          {planSelect(orderSource, s.deployment_order_plans, (id) => set({
            deployment_order: id ? { plan: id } : { custom: [...(order ?? SINNERS)] },
          }))}
          {"custom" in team.deployment_order && <button type="button" onClick={saveOrderPlan}>{t("saveAsPlan")}</button>}
        </div>
        {"custom" in team.deployment_order ? (
          <SinnerGrid order={team.deployment_order.custom} path={`${path}/deployment_order/custom`}
            onChange={(custom) => set({ deployment_order: { custom } })} />
        ) : order && <SinnerGrid order={order} path={`${path}/deployment_order`} />}
      </fieldset>

      <fieldset>
        <legend>{t("team.starlight")}</legend>
        <div className={"row" + (bad(`${path}/starlight`) && !("custom" in team.starlight) ? " bad" : "")}>
          {planSelect(starSource, s.starlight_plans, (id) => set({
            starlight: id ? { plan: id } : {
              custom: starPlan ? { levels: [...starPlan.levels], priority: [...starPlan.priority], convert_leftover: starPlan.convert_leftover } : defaultStarlight(),
            },
          }))}
          {"custom" in team.starlight && <button type="button" onClick={saveStarPlan}>{t("saveAsPlan")}</button>}
        </div>
        {"custom" in team.starlight ? (
          <StarlightEditor value={team.starlight.custom} path={`${path}/starlight/custom`}
            onChange={(custom) => set({ starlight: { custom } })} />
        ) : starPlan && <StarlightEditor value={starPlan} path={`${path}/starlight`} />}
      </fieldset>

      <GiftSearchPanel i={i} />

      <details className="panel" open>
        <summary>{t("team.more")}</summary>
        <div className="options">
          <div className={"toggle" + (bad(`${path}/guard_turns`) ? " bad" : "")}>
            <label className="check">
              <input type="checkbox" checked={team.guard_turns > 0} onChange={(e) => set({ guard_turns: e.target.checked ? 1 : 0 })} />
              {t("team.guard_turns")}
            </label>
            <select value={team.guard_turns || 1} disabled={!team.guard_turns} onChange={(e) => set({ guard_turns: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} {t("team.turns")}</option>)}
            </select>
            <small>{t("team.guard_turns_note")}</small>
          </div>
          <div className={"toggle" + (bad(`${path}/allow_white_gossypium`) ? " bad" : "")}>
            <label className="check">
              <input type="checkbox" checked={team.allow_white_gossypium} onChange={(e) => set({ allow_white_gossypium: e.target.checked })} />
              {t("team.allow_white_gossypium")}
            </label>
            <small>{t("team.allow_white_gossypium_note")}</small>
          </div>
          <div className={"toggle" + (bad(`${path}/usage`) ? " bad" : "")}>
            <label className="check">
              <input type="checkbox" checked={team.usage !== "any"} onChange={(e) => set({ usage: e.target.checked ? "hard_only" : "any" })} />
              {t("team.usage")}
            </label>
            <select value={team.usage === "any" ? "hard_only" : team.usage} disabled={team.usage === "any"}
              onChange={(e) => set({ usage: e.target.value })}>
              {teamEnum("usage").filter((u) => u !== "any").map((u) => <option key={u} value={u}>{tv("usage", u)}</option>)}
            </select>
          </div>
        </div>
        <div className="grid">
          <Field label={t("team.hard_from_floor")} path={`${path}/hard_from_floor`}>
            <Num value={team.hard_from_floor} min={0} max={5} onChange={(v) => set({ hard_from_floor: v })} />
          </Field>
          {pick("heal")}
          <Field label={t("team.reserve_cost")} path={`${path}/reserve_cost`}>
            <Num value={team.reserve_cost} min={0} onChange={(v) => set({ reserve_cost: v })} />
          </Field>
          <Field label={t("team.shop_refresh_limit")} path={`${path}/shop_refresh_limit`}>
            <Num value={team.shop_refresh_limit} min={0} onChange={(v) => set({ shop_refresh_limit: v })} />
          </Field>
          <Field label={t("team.theme_pack_plan")} path={`${path}/theme_pack_plan`}>
            <select value={team.theme_pack_plan} onChange={(e) => set({ theme_pack_plan: e.target.value })}>
              <option value="default">{t("defaultPlan")}</option>
              {s.theme_pack_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              {missing(team.theme_pack_plan !== "default" && team.theme_pack_plan, s.theme_pack_plans)}
            </select>
          </Field>
          {pick("trial_risk_weight")}
          <Field label={t("team.min_alive")} path={`${path}/min_alive`} note={t("team.min_alive_note")}>
            <Num value={team.min_alive} min={0} max={12} onChange={(v) => set({ min_alive: v })} />
          </Field>
        </div>
        <div className={"rewards" + (bad(`${path}/reward_cards`) ? " bad" : "")}>
          <h4>{t("team.reward_cards")}</h4>
          <ReorderList items={team.reward_cards} keyOf={(x) => x} onChange={(reward_cards) => set({ reward_cards })}
            render={(x, j) => <>{j + 1}. {x}</>} />
        </div>
      </details>
    </div>
  );
}

const ROMAN = ["", "I", "II", "III"];

/** E.G.O Gift Search (spec 04 section 9): keyword tabs and tiers like the game's page; a click adds or removes. */
function GiftSearchPanel({ i }: { i: number }) {
  const { s, update, t, bad } = useEditor();
  const team = s.teams[i];
  const search = team.gift_search;
  const path = `teams/${i}/gift_search`;
  const [tab, setTab] = useState(SEARCH_TABS.includes(team.keyword) ? team.keyword : SEARCH_TABS[0]);
  const set = (patch: Partial<Team["gift_search"]>) => update((d) => { Object.assign(d.teams[i].gift_search, patch); });
  const zh = s.language === "zh_tw";
  const nameOf = (g: GiftRef) => {
    const known = SEARCH_GIFTS.find((x) => x.keyword === g.keyword && x.tier === g.tier && x.en === g.name);
    return zh && known?.zh ? known.zh : g.name;
  };
  const rank = (g: SearchGift) => search.gifts.findIndex((x) => x.keyword === g.keyword && x.tier === g.tier && x.name === g.en) + 1;
  const full = search.gifts.length >= MAX_GIFTS;
  const count = (k: string) => search.gifts.filter((g) => g.keyword === k).length;
  return (
    <details className={"panel" + (bad(path) ? " bad" : "")}>
      <summary>{t("gift.title")}{search.enabled && search.gifts.length ? ` (${search.gifts.length})` : ""}</summary>
      <div className="toggle">
        <label className="check">
          <input type="checkbox" checked={search.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("gift.enabled")}
        </label>
        <small>{t("gift.note")}</small>
      </div>
      <div className="gift-search">
        <div className="gift-tabs" role="tablist">
          {SEARCH_TABS.map((k) => (
            <button type="button" key={k} role="tab" aria-selected={k === tab} className={k === tab ? "selected" : ""} onClick={() => setTab(k)}>
              {k}{count(k) > 0 && <b>{count(k)}</b>}
            </button>
          ))}
        </div>
        {[3, 2, 1].map((tier) => (
          <div key={tier} className="gift-tier">
            <h4>{ROMAN[tier]}</h4>
            <div className="gifts">
              {SEARCH_GIFTS.filter((g) => g.keyword === tab && g.tier === tier).map((g) => {
                const n = rank(g);
                return (
                  <button type="button" key={g.en} className={"gift" + (n ? " picked" : "")} aria-pressed={n > 0}
                    disabled={!n && full} title={!n && full ? t("gift.full") : undefined}
                    onClick={() => set({ gifts: toggleGift(search.gifts, { keyword: g.keyword, tier: g.tier, name: g.en }) })}>
                    {n > 0 && <span className="rank">{n}</span>}
                    <span className="name">{zh && g.zh ? g.zh : g.en}</span>
                    {zh && g.zh && <small>{g.en}</small>}
                  </button>
                );
              })}
            </div>
          </div>
        ))}
      </div>
      <div className={"rewards" + (bad(`${path}/gifts`) ? " bad" : "")}>
        <h4>{t("gift.order")} ({search.gifts.length}/{MAX_GIFTS})</h4>
        {full && <p className="muted">{t("gift.full")}</p>}
        {search.gifts.length ? (
          <ReorderList items={search.gifts} keyOf={(g) => `${g.keyword}|${g.tier}|${g.name}`} onChange={(gifts) => set({ gifts })}
            render={(g, j) => (
              <>
                {j + 1}. {nameOf(g)} <small className="muted">{g.keyword} {ROMAN[g.tier]}</small>{" "}
                <button type="button" className="icon" aria-label={t("remove")} title={t("remove")}
                  onClick={(e) => { e.stopPropagation(); set({ gifts: toggleGift(search.gifts, g) }); }}>×</button>
              </>
            )} />
        ) : <p className="muted">{t("gift.none")}</p>}
      </div>
    </details>
  );
}

/** Keep a dangling plan id selectable so the select shows it instead of silently changing it. */
function missing(id: string | false, plans: { id: string }[]) {
  return id && !plans.some((p) => p.id === id) ? <option value={id}>? {id}</option> : null;
}
