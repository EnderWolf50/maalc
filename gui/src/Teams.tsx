// Teams (spec 04 section 9): the list order is the team queue (#501).
import { useRef, useState, type KeyboardEvent } from "react";
import { resetTeamTimes } from "./api";
import { KeywordIcon, TIERS, kwText } from "./KeywordGrid";
import { teamKeyword } from "./gifts";
import { fill } from "./i18n";
import {
  MAX_GIFTS, SEARCH_GIFTS, SEARCH_TABS, SINNERS, defaultStarlight, freeName, newId, newTeam, teamEnum, toggleGift,
  type GiftRef, type SearchGift, type Team,
} from "./model";
import { SinnerGrid, StarlightEditor, StarlightReceipt } from "./Plans";
import { SkillPanel } from "./SkillReplacement";
import { Choice, Field, Input, Mark, Num, ReorderList, Select, ToggleNum, nextTab, useEditor, usePick, useUndo, withBreaks } from "./ui";

export function TeamsTab() {
  const { s, update, t, tv, bad } = useEditor();
  const [i, setSel] = usePick("teams", s.teams);
  const [undoNote, removeAt] = useUndo();
  const remove = () => removeAt(s.teams, i, (fn) => update((d) => fn(d.teams)), setSel);
  return (
    <div className="split">
      <aside className="queue">
        <p className="muted">{t("teams.queue")}</p>
        {s.teams.length ? (
          <ReorderList items={s.teams} keyOf={(x) => x.id} selected={i} onSelect={(j, teams) => setSel(teams[j].id)}
            badAt={(j) => bad(`teams/${j}`)}
            onChange={(teams) => update((d) => { d.teams = teams; })}
            render={(x) => (
              <span className={x.enabled ? "" : "muted"}>{x.name || "—"} <small>TEAMS #{x.game_team}</small>
                {!x.enabled && <em className="qtag off">{t("team.disabled")}</em>}
                {x.usage !== "any" && <em className="qtag">{tv("usage", x.usage)}</em>}
              </span>
            )} />
        ) : <p className={"muted" + (bad("teams") ? " bad" : "")}>{t("noTeams")}</p>}
        {undoNote}
        <button type="button" onClick={() => {
          const n = s.teams.length + 1;
          const team = newTeam(n, `${t("teamName")} ${n}`);
          update((d) => { d.teams.push(team); });
          setSel(team.id);
        }}>+ {t("add")}</button>
        {s.teams[i] && <SectionIndex />}
      </aside>
      <section>{s.teams[i] && <TeamEditor i={i} onRemove={remove} />}</section>
    </div>
  );
}

/** The team page's sections, so a long page is one click from each: a closed panel opens and its summary takes the focus, or a
 * section's first control. */
const SECTIONS = [
  ["order", "team.deployment_order"], ["starlight", "team.starlight"], ["gift", "gift.title"], ["keep", "keep.title"],
  ["skill", "skill.title"], ["more", "team.more"],
] as const;
function SectionIndex() {
  const { t } = useEditor();
  const go = (k: string) => {
    const el = document.querySelector<HTMLElement>(`[data-section="${k}"]`);
    if (!el) return;
    if (el instanceof HTMLDetailsElement) el.open = true;
    el.scrollIntoView?.({ block: "start" });
    el.querySelector<HTMLElement>("summary, select, input, button")?.focus({ preventScroll: true });
  };
  return (
    <nav className="sections" aria-label={t("team.sections")}>
      <small>{t("team.sections")}</small>
      {SECTIONS.map(([k, label]) => <button type="button" key={k} onClick={() => go(k)}>{t(label)}</button>)}
    </nav>
  );
}

function TeamEditor({ i, onRemove }: { i: number; onRemove: () => void }) {
  const { s, update, t, tv, bad, chooseList } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  const main = teamKeyword(team.gift_list, s.gift_lists);
  const [notice, setNotice] = useState<{ team: string; text: string } | null>(null); // shown on its own team only, also when the reset ends after a switch
  const [askReset, setAskReset] = useState(false); // Reset time records asks first, in the page
  // Picking another team drops the question (its Cancel takes the focus); the editor stays mounted, so the panels left open
  // stay open.
  const [shownTeam, setShownTeam] = useState(team.id);
  if (shownTeam !== team.id) { setShownTeam(team.id); setAskReset(false); }

  // "plan id" or "" for custom. Switching to custom copies the plan's values (spec 04 section 9).
  const orderSource = "plan" in team.deployment_order ? team.deployment_order.plan : "";
  const orderPlan = s.deployment_order_plans.find((p) => p.id === orderSource);
  const order = "custom" in team.deployment_order ? team.deployment_order.custom : orderPlan?.order;
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
    <Choice value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("custom")}</option>
      {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      {missing(value, plans)}
    </Choice>
  );

  // Laid out like AALC's team page: who and what on top, the sinner grid, starlight, then the rest.
  return (
    <div className="team" data-path={path}>
      <div className="bar">
        <Field label={t("name")} path={`${path}/name`}>
          <Input value={team.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label={t("team.game_team")} path={`${path}/game_team`}>
          <Num value={team.game_team} min={1} max={40} onChange={(v) => set({ game_team: v })} />
        </Field>
        <Mark as="label" className="check" path={`${path}/enabled`}>
          <Input type="checkbox" checked={team.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("team.enabled")}
        </Mark>
        <span className="spacer" />
        <button type="button" onClick={() => setAskReset(true)}>{t("resetTimes")}</button>
        <button type="button" className="danger" onClick={onRemove}>{t("remove")}</button>
      </div>
      {askReset && (
        // asked in the page, not in a browser dialog: the window has no system frame for one to match
        <div className="notice confirm" role="group" aria-label={t("resetTimes")}>
          <span>{t("resetConfirm")}</span>
          <button type="button" onClick={async () => {
            setAskReset(false);
            try { await resetTeamTimes(team.id); setNotice({ team: team.id, text: t("resetDone") }); }
            catch (e) { setNotice({ team: team.id, text: String(e) }); }
          }}>{t("resetGo")}</button>
          {/* the focus starts on Cancel: the marker cannot be taken back */}
          <button type="button" autoFocus onClick={() => setAskReset(false)}>{t("cancel")}</button>
        </div>
      )}
      {notice?.team === team.id && <p className="notice">{notice.text}</p>}
      {/* What the team plays with, under its name: read and changed without scrolling past the grids. */}
      <div className="bar lists">
        <Field label={t("team.gift_list")} path={`${path}/gift_list`}>
          <span className="inline">
            <Choice value={team.gift_list} onChange={(e) => set({ gift_list: e.target.value })}>
              <option value="default">{t("defaultPlan")}</option>
              {s.gift_lists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              {missing(team.gift_list !== "default" && team.gift_list, s.gift_lists)}
            </Choice>
            <button type="button" disabled={!main} onClick={() => chooseList(team.gift_list, true)}>{t("team.edit_list")}</button>
          </span>
          {main && <small>{t("team.main_keyword")}{t("colon")}<b>{t(kwText(main))}</b></small>}
        </Field>
        <Field label={t("team.theme_pack_plan")} path={`${path}/theme_pack_plan`}>
          <Choice value={team.theme_pack_plan} onChange={(e) => set({ theme_pack_plan: e.target.value })}>
            <option value="default">{t("defaultPlan")}</option>
            {s.theme_pack_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            {missing(team.theme_pack_plan !== "default" && team.theme_pack_plan, s.theme_pack_plans)}
          </Choice>
        </Field>
        <details className="hint">
          <summary>{t("gl.help")}</summary>
          <p>{withBreaks(t("team.gift_list_note"))}</p>
        </details>
      </div>

      <fieldset data-section="order">
        <legend>{t("team.deployment_order")}</legend>
        <Mark className="row" path={`${path}/deployment_order`} marked={!("custom" in team.deployment_order)}>
          {planSelect(orderSource, s.deployment_order_plans, (id) => set({
            deployment_order: id ? { plan: id } : { custom: [...(order ?? SINNERS)] },
          }))}
          {"custom" in team.deployment_order && <button type="button" onClick={saveOrderPlan}>{t("saveAsPlan")}</button>}
        </Mark>
        {"custom" in team.deployment_order ? (
          <SinnerGrid order={team.deployment_order.custom} path={`${path}/deployment_order/custom`}
            onChange={(custom) => set({ deployment_order: { custom } })} />
        ) : order && <>
          <p className="muted">{fill(t("team.plan_note"), { name: orderPlan!.name, tab: t("tab.deployment"), custom: t("custom") })}</p>
          <SinnerGrid order={order} path={`${path}/deployment_order`} />
        </>}
      </fieldset>

      <fieldset data-section="starlight">
        <legend>{t("team.starlight")}</legend>
        <Mark className="row" path={`${path}/starlight`} marked={!("custom" in team.starlight)}>
          {planSelect(starSource, s.starlight_plans, (id) => set({
            starlight: id ? { plan: id } : {
              custom: starPlan ? { levels: [...starPlan.levels], priority: [...starPlan.priority], convert_leftover: starPlan.convert_leftover } : defaultStarlight(),
            },
          }))}
          {"custom" in team.starlight && <button type="button" onClick={saveStarPlan}>{t("saveAsPlan")}</button>}
        </Mark>
        {"custom" in team.starlight ? (
          <StarlightEditor value={team.starlight.custom} path={`${path}/starlight/custom`}
            onChange={(custom) => set({ starlight: { custom } })} />
        ) : starPlan && <>
          {/* a plan is edited on its own tab: here its picks on one line, the cards folded away */}
          <p className="muted">{fill(t("team.plan_note"), { name: starPlan.name, tab: t("tab.starlight"), custom: t("custom") })}</p>
          <StarlightReceipt value={starPlan} />
          <details className="hint">
            <summary>{t("starlight.cards")}</summary>
            <StarlightEditor value={starPlan} path={`${path}/starlight`} />
          </details>
        </>}
      </fieldset>

      <GiftSearchPanel i={i} />
      <KeepPanel i={i} />
      <SkillPanel i={i} />

      <details className="panel" open data-section="more">
        <summary>{t("team.more")}</summary>
        <div className="options">
          <Mark className="toggle" path={`${path}/guard_turns`}>
            <label className="check">
              <Input type="checkbox" checked={team.guard_turns > 0} onChange={(e) => set({ guard_turns: e.target.checked ? 1 : 0 })} />
              {t("team.guard_turns")}
            </label>
            <Choice value={team.guard_turns || 1} disabled={!team.guard_turns} onChange={(e) => set({ guard_turns: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} {t("team.turns")}</option>)}
            </Choice>
            <small>{t("team.guard_turns_note")}</small>
          </Mark>
          <ToggleNum label={t("team.hard_from_floor")} path={`${path}/hard_from_floor`} value={team.hard_from_floor} on={1} min={1} max={5}
            note={t("team.hard_from_floor_note")} onChange={(v) => set({ hard_from_floor: v })} />
          <Mark className="toggle" path={`${path}/allow_white_gossypium`}>
            <label className="check">
              <Input type="checkbox" checked={team.allow_white_gossypium} onChange={(e) => set({ allow_white_gossypium: e.target.checked })} />
              {t("team.allow_white_gossypium")}
            </label>
            <small>{t("team.allow_white_gossypium_note")}</small>
          </Mark>
          <Mark className="toggle" path={`${path}/usage`}>
            <label className="check">
              <Input type="checkbox" checked={team.usage !== "any"} onChange={(e) => set({ usage: e.target.checked ? "hard_only" : "any" })} />
              {t("team.usage")}
            </label>
            <Choice value={team.usage === "any" ? "hard_only" : team.usage} disabled={team.usage === "any"}
              onChange={(e) => set({ usage: e.target.value })}>
              {teamEnum("usage").filter((u) => u !== "any").map((u) => <option key={u} value={u}>{tv("usage", u)}</option>)}
            </Choice>
          </Mark>
        </div>
        <div className="grid">
          <Field label={t("team.heal")} path={`${path}/heal`}>
            <Select value={team.heal} options={teamEnum("heal")} label={(v) => tv("heal", v)} onChange={(v) => set({ heal: v })} />
          </Field>
          <Field label={t("team.reserve_cost")} path={`${path}/reserve_cost`}>
            <Num value={team.reserve_cost} min={0} onChange={(v) => set({ reserve_cost: v })} />
          </Field>
          <Field label={t("team.shop_refresh_keyword")} path={`${path}/shop_refresh_keyword`}>
            <Num value={team.shop_refresh_keyword} min={0} onChange={(v) => set({ shop_refresh_keyword: v })} />
          </Field>
          <Field label={t("team.shop_refresh_normal")} path={`${path}/shop_refresh_normal`} note={t("team.shop_refresh_note")}>
            <Num value={team.shop_refresh_normal} min={0} onChange={(v) => set({ shop_refresh_normal: v })} />
          </Field>
          <Field label={t("team.min_alive")} path={`${path}/min_alive`} note={t("team.min_alive_note")}>
            <Num value={team.min_alive} min={0} max={12} onChange={(v) => set({ min_alive: v })} />
          </Field>
        </div>
        <div className={"rewards" + (bad(`${path}/reward_cards`) ? " bad" : "")} data-path={`${path}/reward_cards`}>
          <h3>{t("team.reward_cards")}</h3>
          <ReorderList items={team.reward_cards} keyOf={(x) => x} onChange={(reward_cards) => set({ reward_cards })}
            render={(x, j) => <>{j + 1}. {x}</>} />
        </div>
      </details>
    </div>
  );
}

const sameRef = (a: GiftRef, g: SearchGift) => a.keyword === g.keyword && a.tier === g.tier && a.name === g.en;

/** A gift's name in the GUI's language: the Chinese one when the data has it. */
function refName(g: GiftRef, zh: boolean) {
  const known = SEARCH_GIFTS.find((x) => sameRef(g, x));
  return zh && known?.zh ? known.zh : g.name;
}

/** The E.G.O Gift Search page's gifts, keyword tabs and tiers like the game's page; a click adds or removes one.
 * mark: what a picked gift shows (its place in the list), null when it is not picked. */
function GiftGrid({ gifts, start, full, mark, onToggle }: {
  gifts: GiftRef[]; start: string; full: boolean; mark: (g: SearchGift) => string | null; onToggle: (g: GiftRef) => void;
}) {
  const { s, t } = useEditor();
  const [tab, setTab] = useState(SEARCH_TABS.includes(start) ? start : SEARCH_TABS[0]);
  const zh = s.language === "zh_tw";
  const count = (k: string) => gifts.filter((g) => g.keyword === k).length;
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});
  const walk = (e: KeyboardEvent) => {
    const next = nextTab(SEARCH_TABS, tab, e.key);
    if (!next || next === tab) return;
    e.preventDefault();
    setTab(next);
    refs.current[next]?.focus();
  };
  return (
    <div className="gift-search">
      <div className="gift-tabs" role="tablist" onKeyDown={walk}>
        {SEARCH_TABS.map((k) => (
          <button type="button" key={k} role="tab" aria-selected={k === tab} tabIndex={k === tab ? 0 : -1} className={k === tab ? "selected" : ""}
            ref={(el) => { refs.current[k] = el; }} onClick={() => setTab(k)}>
            <KeywordIcon keyword={k} />{t(kwText(k))}{count(k) > 0 && <b>{count(k)}</b>}
          </button>
        ))}
      </div>
      {[3, 2, 1].map((tier) => (
        <div key={tier} className="gift-tier">
          <h3>{TIERS[tier]}</h3>
          <div className="gifts">
            {SEARCH_GIFTS.filter((g) => g.keyword === tab && g.tier === tier).map((g) => {
              const m = mark(g);
              return (
                <button type="button" key={g.en} className={"gift" + (m ? " picked" : "")} aria-pressed={!!m}
                  disabled={!m && full} title={!m && full ? t("gift.full") : undefined}
                  onClick={() => onToggle({ keyword: g.keyword, tier: g.tier, name: g.en })}>
                  {m && <span className="rank">{m}</span>}
                  <span className="name">{zh && g.zh ? g.zh : g.en}</span>
                  {zh && g.zh && <small>{g.en}</small>}
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

/** What the shop may sell (spec 04 section 9): the highest tier and the vestiges. What it buys, keeps and fuses is the team's
 * gift list (spec 04 section 13). */
function KeepPanel({ i }: { i: number }) {
  const { s, update, t, bad } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  return (
    <details className={"panel" + (["sell_max_tier", "sell_vestiges"].some((k) => bad(`${path}/${k}`)) ? " bad" : "")} data-section="keep">
      <summary>{t("keep.title")}</summary>
      <p className="muted">{t("keep.note")}</p>
      <div className="options">
        <Mark className="toggle" path={`${path}/sell_max_tier`}>
          <span>{t("keep.sell_max_tier")}</span>
          <Choice value={team.sell_max_tier} onChange={(e) => set({ sell_max_tier: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{TIERS[n]}</option>)}
          </Choice>
          <small>{t("keep.sell_max_tier_note")}</small>
        </Mark>
        <Mark className="toggle" path={`${path}/sell_vestiges`}>
          <label className="check">
            <Input type="checkbox" checked={team.sell_vestiges} onChange={(e) => set({ sell_vestiges: e.target.checked })} />
            {t("keep.sell_vestiges")}
          </label>
          <small>{withBreaks(t("keep.sell_vestiges_note"))}</small>
        </Mark>
      </div>
    </details>
  );
}

/** E.G.O Gift Search (spec 04 section 9): keyword tabs and tiers like the game's page; a click adds or removes. */
function GiftSearchPanel({ i }: { i: number }) {
  const { s, update, t, bad } = useEditor();
  const team = s.teams[i];
  const search = team.gift_search;
  const main = teamKeyword(team.gift_list, s.gift_lists);
  const path = `teams/${i}/gift_search`;
  const set = (patch: Partial<Team["gift_search"]>) => update((d) => { Object.assign(d.teams[i].gift_search, patch); });
  const zh = s.language === "zh_tw";
  const rank = (g: SearchGift) => search.gifts.findIndex((x) => sameRef(x, g)) + 1;
  const full = search.gifts.length >= MAX_GIFTS;
  return (
    <details className={"panel" + (bad(path) ? " bad" : "")} data-path={path} data-section="gift">
      <summary>{t("gift.title")}{search.enabled && search.gifts.length ? ` (${search.gifts.length})` : ""}</summary>
      <Mark className="toggle" path={`${path}/enabled`}>
        <label className="check">
          <Input type="checkbox" checked={search.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("gift.enabled")}
        </label>
        <small className="caution">{t("gift.note")}</small>
      </Mark>
      <GiftGrid key={team.id} gifts={search.gifts} start={main ?? SEARCH_TABS[0]} full={full} mark={(g) => (rank(g) ? String(rank(g)) : null)}
        onToggle={(g) => set({ gifts: toggleGift(search.gifts, g) })} />
      <div className={"rewards" + (bad(`${path}/gifts`) ? " bad" : "")} data-path={`${path}/gifts`}>
        <h3>{t("gift.order")} ({search.gifts.length}/{MAX_GIFTS})</h3>
        {full && <p className="muted">{t("gift.full")}</p>}
        {search.gifts.length ? (
          <ReorderList items={search.gifts} keyOf={(g) => `${g.keyword}|${g.tier}|${g.name}`} onChange={(gifts) => set({ gifts })}
            render={(g, j) => (
              <>
                {j + 1}. {refName(g, zh)} <small className="muted">{t(kwText(g.keyword))} {TIERS[g.tier]}</small>{" "}
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
