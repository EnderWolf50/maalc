// Teams (spec 04 section 9): the list order is the team queue (#501).
import { useState } from "react";
import { resetTeamTimes } from "./api";
import { TIERS, kwText } from "./KeywordGrid";
import { teamKeyword } from "./gifts";
import {
  MAX_GIFTS, SEARCH_GIFTS, SEARCH_TABS, SINNERS, defaultStarlight, freeName, newId, newTeam, starlightCost, teamEnum, toggleGift,
  type GiftRef, type SearchGift, type Settings, type Team,
} from "./model";
import { fill, type Key } from "./i18n";
import { Row, Section, ToggleRow } from "./frame";
import { SinnerGrid, StarlightEditor } from "./Plans";
import { SkillPanel } from "./SkillReplacement";
import { Field, GLYPHS, Icon, Num, ReorderList, Select, useEditor, usePick, useUndo } from "./ui";

/** Which team the next run plays, per difficulty the run can begin on: the first enabled team whose usage fits, as the bot's
 * agent/team_queue.py pick_team takes it. A fixed difficulty begins on itself; auto begins HARD while weekly bonuses are left
 * and NORMAL after, and a target past floor 5 is always HARD (spec 04, 自動難度). */
export function nextTeams(s: Settings): { difficulties: Difficulty[]; picks: { difficulty: Difficulty; id: string }[] } {
  // auto runs NORMAL only once the weekly bonuses are out, and with 每週獎勵用完就停 the bot ends there instead
  // (agent/actions.py, before run_difficulty)
  const difficulties: Difficulty[] = s.run.difficulty !== "auto" ? [s.run.difficulty as Difficulty]
    : s.run.target_floor > 5 || s.run.stop_when_weekly_bonus_out ? ["hard"] : ["hard", "normal"];
  const picks = difficulties.flatMap((difficulty) => {
    const team = s.teams.find((x) => x.enabled && (x.usage === "any" || x.usage === `${difficulty}_only`));
    return team ? [{ difficulty, id: team.id }] : [];
  });
  return { difficulties, picks };
}
type Difficulty = "hard" | "normal";

export function TeamsTab() {
  const { s, update, t, tv, bad } = useEditor();
  const [i, setSel] = usePick("teams", s.teams);
  const next = nextTeams(s);
  // a team the next run plays whatever its difficulty: "下一局"; else it says for which difficulty
  const nextTag = (id: string) => {
    const mine = next.picks.filter((x) => x.id === id);
    if (!mine.length) return null;
    const text = mine.length === next.difficulties.length ? t("queue.next")
      : [t("queue.next"), ...mine.map((x) => tv("difficulty", x.difficulty))].join(t("sum.sep"));
    return <small className="next-tag">{text}</small>;
  };
  const [undoNote, removeAt] = useUndo();
  const remove = () => removeAt(s.teams, i, (fn) => update((d) => fn(d.teams)), setSel);
  return (<>
    <p className="page-note">{t("teams.queue")}</p>
    <div className="split">
      <aside>
        <button type="button" className="add" onClick={() => {
          const n = s.teams.length + 1;
          const team = newTeam(n, `${t("teamName")} ${n}`);
          update((d) => { d.teams.push(team); });
          setSel(team.id);
        }}>+ {t("add")}</button>
        {s.teams.length ? (
          <ReorderList items={s.teams} keyOf={(x) => x.id} selected={i} onSelect={(j, teams) => setSel(teams[j].id)}
            badAt={(j) => bad(`teams/${j}`)} label={t("tab.teams")}
            onChange={(teams) => update((d) => { d.teams = teams; })}
            render={(x) => (
              <span className={"queue-row" + (x.enabled ? "" : " off")}>
                <span className="nm">{x.name || "—"}</span> <small className="slot">#{x.game_team}</small>
                {(nextTag(x.id) || !x.enabled || x.usage !== "any") && <span className="tags">
                  {nextTag(x.id)}
                  {!x.enabled && <small className="off-tag">{t("team.off")}</small>}
                  {x.usage !== "any" && <small className="off-tag">{tv("usage", x.usage)}</small>}
                </span>}
              </span>
            )} />
        ) : <p className={"empty-note" + (bad("teams") ? " bad" : "")}>{t("noTeams")}</p>}
        {undoNote}
      </aside>
      <section>{s.teams[i] && <TeamEditor i={i} onRemove={remove} />}</section>
    </div>
  </>);
}

function TeamEditor({ i, onRemove }: { i: number; onRemove: () => void }) {
  const { s, update, t, tv, bad, chooseList, pick, openTab } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  const main = teamKeyword(team.gift_list, s.gift_lists);
  const [notice, setNotice] = useState("");
  // the team's own order or graces, put away when it moved to a plan: 復原 brings them back (gone on another team)
  const [putAway, setPutAway] = useState<{ team: string; name: string; back: Partial<Team> } | null>(null);
  const toPlan = (what: "deployment_order" | "starlight", id: string, name: string) => {
    if ("custom" in team[what]) setPutAway({ team: team.id, name, back: { [what]: team[what] } });
    set({ [what]: { plan: id } });
  };

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

  const planSelect = (value: string, plans: { id: string; name: string }[], onChange: (id: string) => void, label: string) => (
    <select value={value} aria-label={label} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("custom")}</option>
      {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      {missing(value, plans)}
    </select>
  );

  // What each section holds, for its header: a folded section still says what is set.
  const deployed = order ? order.length : 0;
  const orderName = orderSource ? s.deployment_order_plans.find((p) => p.id === orderSource)?.name ?? orderSource : t("custom");
  const starName = starSource ? starPlan?.name ?? starSource : t("custom");
  const listName = team.gift_list === "default" ? t("defaultPlan") : s.gift_lists.find((l) => l.id === team.gift_list)?.name ?? team.gift_list;
  const packName = team.theme_pack_plan === "default" ? t("defaultPlan")
    : s.theme_pack_plans.find((p) => p.id === team.theme_pack_plan)?.name ?? team.theme_pack_plan;
  const picked = star ? star.levels.filter((l) => l !== "none").length : 0;
  const sep = t("sum.sep");
  // only what links to a plan, each with its label: custom and default are the plain case
  const linked: [boolean, Key, string][] = [[!!orderSource, "team.deployment_order", orderName], [!!starSource, "team.starlight", starName],
    [team.gift_list !== "default", "team.gift_list", listName], [team.theme_pack_plan !== "default", "team.theme_pack_plan", packName]];
  const plansSum = linked.filter(([on]) => on).map(([, key, name]) => `${t(key)} ${name}`).join(sep) || t("sum.plans_none");
  // a team on a plan opens it where it is edited (the gift list's 編輯這份清單 does the same)
  const editPlan = (list: "deployment_order_plans" | "starlight_plans" | "theme_pack_plans", id: string, tab: string, what: Key) => (
    <button type="button" aria-label={`${t("plan.edit")}${t("sum.sep")}${t(what)}`} onClick={() => { pick(list, id); openTab?.(tab); }}>
      {t("plan.edit")}</button>
  );
  const battleSum = [team.guard_turns ? fill(t("sum.guard"), { n: team.guard_turns }) : "",
    team.hard_from_floor === null ? "" : fill(t("sum.hard_from"), { n: team.hard_from_floor }),
    team.usage === "any" ? "" : tv("usage", team.usage), tv("heal", team.heal),
    team.min_alive ? fill(t("sum.min_alive"), { n: team.min_alive }) : ""].filter(Boolean).join(sep);
  const orderCustom = "custom" in team.deployment_order, starCustom = "custom" in team.starlight;

  // Laid out like AALC's team page: who on top, then which plans it uses, the sinner grid, starlight, then the rest.
  return (
    <div className="team" data-path={path}>
      <div className="bar">
        <Field label={t("name")} path={`${path}/name`}>
          <input value={team.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label={t("team.game_team")} path={`${path}/game_team`}>
          <Num value={team.game_team} min={1} max={40} onChange={(v) => set({ game_team: v })} />
        </Field>
        <label className="check switch-label" data-path={`${path}/enabled`}><input type="checkbox" className="switch" checked={team.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("team.enabled")}</label>
        <span className="spacer" />
        <button type="button" className="subtle danger" onClick={onRemove}>
          <Icon glyph={GLYPHS.remove} />{t("remove")}</button>
      </div>
      {notice && <p className="notice">{notice}</p>}
      {putAway?.team === team.id && (
        <p className="notice" aria-live="polite">{fill(t("plan.switched"), { name: putAway.name })}{" "}
          <button type="button" onClick={() => { set(putAway.back); setPutAway(null); }}>{t("undo")}</button>
        </p>
      )}

      <Section id="team.plans" title={t("team.plans")} open summary={plansSum}>
        <div className="srows">
          {/* the choice first, the button after it: a problem in the row focuses the row's first control (focusPath) */}
          <Row many label={t("team.deployment_order")} path={`${path}/deployment_order`} mark={bad(`${path}/deployment_order`) && !orderCustom}
            control={<>
              {planSelect(orderSource, s.deployment_order_plans, (id) => (id
                ? toPlan("deployment_order", id, s.deployment_order_plans.find((p) => p.id === id)?.name ?? id)
                : set({ deployment_order: { custom: [...(order ?? SINNERS)] } })), t("team.deployment_order"))}
              {orderCustom ? <button type="button" onClick={saveOrderPlan}>{t("saveAsPlan")}</button>
                : editPlan("deployment_order_plans", orderSource, "deployment", "team.deployment_order")}
            </>} />
          <Row many label={t("team.starlight")} path={`${path}/starlight`} mark={bad(`${path}/starlight`) && !starCustom}
            control={<>
              {planSelect(starSource, s.starlight_plans, (id) => (id
                ? toPlan("starlight", id, s.starlight_plans.find((p) => p.id === id)?.name ?? id)
                : set({ starlight: {
                  custom: starPlan ? { levels: [...starPlan.levels], priority: [...starPlan.priority], convert_leftover: starPlan.convert_leftover } : defaultStarlight(),
                } })), t("team.starlight"))}
              {starCustom ? <button type="button" onClick={saveStarPlan}>{t("saveAsPlan")}</button>
                : editPlan("starlight_plans", starSource, "starlight", "team.starlight")}
            </>} />
          <Row many label={t("team.gift_list")} path={`${path}/gift_list`} note={t("team.gift_list_note")} control={<>
            <select aria-label={t("team.gift_list")} value={team.gift_list} onChange={(e) => set({ gift_list: e.target.value })}>
              <option value="default">{t("defaultPlan")}</option>
              {s.gift_lists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              {missing(team.gift_list !== "default" && team.gift_list, s.gift_lists)}
            </select>
            <button type="button" disabled={!main} onClick={() => chooseList(team.gift_list, true)}>{t("team.edit_list")}</button>
          </>}>
            {main && <small>{t("team.main_keyword")}: <b>{t(kwText(main))}</b></small>}
          </Row>
          <Row many label={t("team.theme_pack_plan")} path={`${path}/theme_pack_plan`} control={<>
            <select aria-label={t("team.theme_pack_plan")} value={team.theme_pack_plan} onChange={(e) => set({ theme_pack_plan: e.target.value })}>
              <option value="default">{t("defaultPlan")}</option>
              {s.theme_pack_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              {missing(team.theme_pack_plan !== "default" && team.theme_pack_plan, s.theme_pack_plans)}
            </select>
            {team.theme_pack_plan !== "default" && editPlan("theme_pack_plans", team.theme_pack_plan, "themepacks", "team.theme_pack_plan")}
          </>} />
        </div>
      </Section>

      <Section key={orderCustom ? "order-own" : "order-plan"} id={orderCustom ? "team.order" : "team.order.plan"} title={t("team.deployment_order")}
        open={orderCustom} bad={bad(`${path}/deployment_order`)}
        summary={fill(t("sum.order"), { d: Math.min(deployed, 7), b: Math.max(deployed - 7, 0) })}>
        {"custom" in team.deployment_order ? (
          <SinnerGrid order={team.deployment_order.custom} path={`${path}/deployment_order/custom`}
            onChange={(custom) => set({ deployment_order: { custom } })} />
        ) : order && <SinnerGrid order={order} path={`${path}/deployment_order`} />}
      </Section>

      <Section key={starCustom ? "star-own" : "star-plan"} id={starCustom ? "team.starlight" : "team.starlight.plan"} title={t("team.starlight")}
        open={starCustom} bad={bad(`${path}/starlight`)}
        summary={[fill(t("sum.stars"), { n: picked, cost: star ? starlightCost(star.levels) : 0 }), star?.convert_leftover ? t("sum.convert") : ""]
        .filter(Boolean).join(t("sum.sep"))}>
        {"custom" in team.starlight ? (
          <StarlightEditor value={team.starlight.custom} path={`${path}/starlight/custom`}
            onChange={(custom) => set({ starlight: { custom } })} />
        ) : starPlan && <StarlightEditor value={starPlan} path={`${path}/starlight`} />}
      </Section>

      <GiftSearchPanel i={i} />
      <ShopPanel i={i} />
      <SkillPanel i={i} />

      <Section id="team.battle" title={t("team.battle")} className="panel" summary={battleSum}
        bad={["guard_turns", "hard_from_floor", "usage", "heal", "min_alive", "reward_cards"].some((k) => bad(`${path}/${k}`))}>
        <div className="srows">
          <Row many label={t("team.guard_turns")} path={`${path}/guard_turns`} note={t("team.guard_turns_note")} control={<>
            <input type="checkbox" className="switch" aria-label={t("team.guard_turns")} checked={team.guard_turns > 0}
              onChange={(e) => set({ guard_turns: e.target.checked ? 1 : 0 })} />
            <select aria-label={t("team.guard_turns")} value={team.guard_turns || 1} disabled={!team.guard_turns}
              onChange={(e) => set({ guard_turns: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} {t("team.turns")}</option>)}
            </select>
          </>} />
          <ToggleRow label={t("team.hard_from_floor")} path={`${path}/hard_from_floor`} value={team.hard_from_floor} on={1} min={1} max={5}
            note={t("team.hard_from_floor_note")} onChange={(v) => set({ hard_from_floor: v })} />
          <Row many label={t("team.usage")} path={`${path}/usage`} control={<>
            <input type="checkbox" className="switch" aria-label={t("team.usage")} checked={team.usage !== "any"}
              onChange={(e) => set({ usage: e.target.checked ? "hard_only" : "any" })} />
            <select aria-label={t("team.usage")} value={team.usage === "any" ? "hard_only" : team.usage} disabled={team.usage === "any"}
              onChange={(e) => set({ usage: e.target.value })}>
              {teamEnum("usage").filter((u) => u !== "any").map((u) => <option key={u} value={u}>{tv("usage", u)}</option>)}
            </select>
          </>} />
          <Row label={t("team.heal")} path={`${path}/heal`}
            control={<Select value={team.heal} options={teamEnum("heal")} label={(v) => tv("heal", v)} onChange={(v) => set({ heal: v })} />} />
          <Row label={t("team.min_alive")} path={`${path}/min_alive`} note={t("team.min_alive_note")}
            control={<Num value={team.min_alive} min={0} max={12} onChange={(v) => set({ min_alive: v })} />} />
          <Row many label={t("team.reward_cards")} path={`${path}/reward_cards`} control={
            <span className="rewards">
              <ReorderList items={team.reward_cards} keyOf={(x) => x} onChange={(reward_cards) => set({ reward_cards })}
                label={t("team.reward_cards")} render={(x, j) => <>{j + 1}. {x}</>} />
            </span>}>
            <small>{t("dragHint")}</small><small>{t("list.keys")}</small>
          </Row>
          <Row many label={t("team.times")} note={t("team.times_note")} control={
            <button type="button" onClick={async () => {
              if (!confirm(t("resetConfirm"))) return;
              try { await resetTeamTimes(team.id); setNotice(t("resetDone")); } catch (e) { setNotice(String(e)); }
            }}><Icon glyph={GLYPHS.reset} />{t("resetTimes")}</button>} />
        </div>
      </Section>
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
  return (
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

/** The shop (spec 04 section 9): the reserve, the refreshes, White Gossypium, the highest tier it may sell and the vestiges. What it
 * buys, keeps and fuses is the team's gift list (spec 04 section 13). */
function ShopPanel({ i }: { i: number }) {
  const { s, update, t, bad } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  const keys = ["reserve_cost", "shop_refresh_keyword", "shop_refresh_normal", "allow_white_gossypium", "sell_max_tier", "sell_vestiges"];
  return (
    <Section id="team.shop" className="panel" title={t("team.shop")} bad={keys.some((k) => bad(`${path}/${k}`))}
      summary={[fill(t("sum.reserve"), { n: team.reserve_cost }),
        fill(t("sum.refresh"), { k: team.shop_refresh_keyword, n: team.shop_refresh_normal }), fill(t("sum.sell"), { tier: TIERS[team.sell_max_tier] }),
        team.sell_vestiges ? t("sum.vestiges") : "", team.allow_white_gossypium ? t("sum.gossypium") : ""].filter(Boolean).join(t("sum.sep"))}>
      <p className="muted hint">{t("keep.note")}</p>
      <div className="srows">
        <Row label={t("team.reserve_cost")} path={`${path}/reserve_cost`}
          control={<Num value={team.reserve_cost} min={0} onChange={(v) => set({ reserve_cost: v })} />} />
        <Row label={t("team.shop_refresh_keyword")} path={`${path}/shop_refresh_keyword`}
          control={<Num value={team.shop_refresh_keyword} min={0} onChange={(v) => set({ shop_refresh_keyword: v })} />} />
        <Row label={t("team.shop_refresh_normal")} path={`${path}/shop_refresh_normal`} note={t("team.shop_refresh_note")}
          control={<Num value={team.shop_refresh_normal} min={0} onChange={(v) => set({ shop_refresh_normal: v })} />} />
        <Row label={t("keep.sell_max_tier")} path={`${path}/sell_max_tier`} note={t("keep.sell_max_tier_note")} control={
          <select value={team.sell_max_tier} onChange={(e) => set({ sell_max_tier: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{TIERS[n]}</option>)}
          </select>} />
        <Row label={t("keep.sell_vestiges")} path={`${path}/sell_vestiges`} note={t("keep.sell_vestiges_note")}
          check={<input type="checkbox" className="switch" checked={team.sell_vestiges} onChange={(e) => set({ sell_vestiges: e.target.checked })} />} />
        <Row label={t("team.allow_white_gossypium")} path={`${path}/allow_white_gossypium`} note={t("team.allow_white_gossypium_note")}
          check={<input type="checkbox" className="switch" checked={team.allow_white_gossypium} onChange={(e) => set({ allow_white_gossypium: e.target.checked })} />} />
      </div>
    </Section>
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
    <Section id="team.gifts" className="panel" title={t("gift.title")} bad={bad(path)} path={path}
      summary={search.enabled ? fill(t("sum.gifts"), { n: search.gifts.length }) : t("sum.off")}>
      <div className="srows">
        <Row label={t("gift.enabled")} note={t("gift.note")}
          check={<input type="checkbox" className="switch" checked={search.enabled} onChange={(e) => set({ enabled: e.target.checked })} />} />
      </div>
      <GiftGrid gifts={search.gifts} start={main ?? SEARCH_TABS[0]} full={full} mark={(g) => (rank(g) ? String(rank(g)) : null)}
        onToggle={(g) => set({ gifts: toggleGift(search.gifts, g) })} />
      <div className={"rewards" + (bad(`${path}/gifts`) ? " bad" : "")} data-path={`${path}/gifts`}>
        <h3 className="sub">{t("gift.order")} ({search.gifts.length}/{MAX_GIFTS})</h3>
        {search.gifts.length > 1 && <p className="muted hint">{[t("dragHint"), t("list.keys")].join(t("sum.sep"))}</p>}
        {full && <p className="muted">{t("gift.full")}</p>}
        {search.gifts.length ? (
          <ReorderList items={search.gifts} keyOf={(g) => `${g.keyword}|${g.tier}|${g.name}`} onChange={(gifts) => set({ gifts })} label={t("gift.order")}
            render={(g, j) => (
              <>
                {j + 1}. {refName(g, zh)} <small className="muted">{g.keyword} {TIERS[g.tier]}</small>{" "}
                <button type="button" className="icon" aria-label={t("remove")} title={t("remove")}
                  onClick={(e) => { e.stopPropagation(); set({ gifts: toggleGift(search.gifts, g) }); }}><Icon glyph={GLYPHS.close} /></button>
              </>
            )} />
        ) : <p className="muted">{t("gift.none")}</p>}
      </div>
    </Section>
  );
}

/** Keep a dangling plan id selectable so the select shows it instead of silently changing it. */
function missing(id: string | false, plans: { id: string }[]) {
  return id && !plans.some((p) => p.id === id) ? <option value={id}>? {id}</option> : null;
}
