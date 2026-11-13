// Teams (spec 04 section 9): the list order is the team queue (#501).
import { useEffect, useRef, useState, type ReactNode, type RefObject } from "react";
import { resetTeamTimes } from "./api";
import { TIERS, kwText } from "./KeywordGrid";
import { teamKeyword } from "./gifts";
import { fill } from "./i18n";
import {
  MAX_GIFTS, SEARCH_GIFTS, SEARCH_TABS, SINNERS, defaultStarlight, freeName, newId, newTeam, starlightCost, teamEnum, toggleGift,
  type GiftRef, type SearchGift, type Team,
} from "./model";
import { SinnerGrid, StarlightEditor } from "./Plans";
import { SkillPanel } from "./SkillReplacement";
import { Field, Num, ProblemMark, ReorderList, Select, ToggleNum, tabKeys, useEditor, withBreaks } from "./ui";

export function TeamsTab() {
  const { s, update, t, bad } = useEditor();
  const [sel, setSel] = useState(s.teams[0]?.id); // by id: the team stays in the editor when the Agent moves it (#501)
  const i = Math.max(0, s.teams.findIndex((x) => x.id === sel));
  return (
    <div className="split">
      <aside>
        {s.teams.length ? (
          <ReorderList className="queue" numbered items={s.teams} keyOf={(x) => x.id} selected={i} onSelect={(j, teams) => setSel(teams[j].id)}
            badAt={(j) => bad(`teams/${j}`)}
            onChange={(teams) => update((d) => { d.teams = teams; })}
            render={(x) => (
              <span className={x.enabled ? "" : "muted"}>{x.name || "—"} <small>#{x.game_team}</small></span>
            )} />
        ) : <p className={"muted" + (bad("teams") ? " bad" : "")}>{t("noTeams")}</p>}
        <button type="button" onClick={() => {
          const n = s.teams.length + 1;
          const team = newTeam(n, `${t("teamName")} ${n}`);
          update((d) => { d.teams.push(team); });
          setSel(team.id);
        }}>+ {t("add")}</button>
        <p className="muted">{t("teams.queue")}</p>
      </aside>
      <section>{s.teams[i] && <TeamEditor i={i} onRemove={() => setSel(s.teams[i - 1]?.id)} />}</section>
    </div>
  );
}

function TeamEditor({ i, onRemove }: { i: number; onRemove: () => void }) {
  const { s, update, t, tv, bad, chooseList } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  const main = teamKeyword(team.gift_list, s.gift_lists);
  const [notice, setNotice] = useState("");
  const page = useRef<HTMLDivElement>(null);
  const inView = useInView(page);

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

  const planSelect = (label: string, value: string, plans: { id: string; name: string }[], onChange: (id: string) => void) => (
    <select aria-label={label} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{t("custom")}</option>
      {plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      {missing(value, plans)}
    </select>
  );

  // Laid out like AALC's team page: who and what on top, the sinner grid, starlight, then the rest.
  return (
    <div className="team" ref={page}>
      <div className="bar">
        <Field label={t("name")} path={`${path}/name`}>
          <input value={team.name} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label={t("team.game_team")} path={`${path}/game_team`}>
          <Num value={team.game_team} min={1} max={40} onChange={(v) => set({ game_team: v })} />
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
      {/* The page runs about seven screens: a row of its sections, which stays at the top while it scrolls, opens one and goes
          there; a section holding a wrong field is red here too. */}
      <div className="jump" role="navigation" aria-label={t("team.sections")}>
        {SECTIONS.map(([key, title, fields]) => {
          const wrong = badIn(bad, path, [...fields]) !== "";
          return (
            <button type="button" key={key} className={wrong ? "bad" : ""} aria-current={inView === key ? "location" : undefined}
              onClick={(e) => jumpTo(e.currentTarget, key)}>
              {t(title).replace(/[（(].*$/, "")}<ProblemMark on={wrong} />
            </button>
          );
        })}
      </div>

      {/* What the shop buys and which packs the team takes: chosen here, near the top, edited on their own tabs. Every section
          is a panel with one header style; the short ones and the sinner grid and starlight start open, Gift Search, shop sales
          and skill replacement closed (their summaries say what they hold). */}
      <details className="panel" open data-sec="lists">
        <summary className={badIn(bad, path, ["gift_list", "theme_pack_plan"])}>{t("team.lists")}<Holds>{listName(team.gift_list, s.gift_lists, t("defaultPlan"))} · {listName(team.theme_pack_plan, s.theme_pack_plans, t("defaultPlan"))}</Holds><ProblemMark on={badIn(bad, path, ["gift_list", "theme_pack_plan"]) !== ""} /></summary>
        <div className="rows">
          <Field label={t("team.gift_list")} path={`${path}/gift_list`} note={t("team.gift_list_note")}>
            <span className="inline">
              <select value={team.gift_list} onChange={(e) => set({ gift_list: e.target.value })}>
                <option value="default">{t("defaultPlan")}</option>
                {s.gift_lists.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
                {missing(team.gift_list !== "default" && team.gift_list, s.gift_lists)}
              </select>
              <button type="button" disabled={!main} onClick={() => chooseList(team.gift_list, true)}>{t("team.edit_list")}</button>
            </span>
            {main && <small>{t("team.main_keyword")}{s.language === "zh_tw" ? "：" : ": "}<b>{t(kwText(main))}</b></small>}
          </Field>
          <Field label={t("team.theme_pack_plan")} path={`${path}/theme_pack_plan`}>
            <select value={team.theme_pack_plan} onChange={(e) => set({ theme_pack_plan: e.target.value })}>
              <option value="default">{t("defaultPlan")}</option>
              {s.theme_pack_plans.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
              {missing(team.theme_pack_plan !== "default" && team.theme_pack_plan, s.theme_pack_plans)}
            </select>
          </Field>
        </div>
      </details>

      <details className="panel" open data-sec="deployment">
        <summary className={badIn(bad, path, ["deployment_order"])}>{t("team.deployment_order")}<Holds>{orderSource ? listName(orderSource, s.deployment_order_plans, t("defaultPlan")) : t("custom")}</Holds><ProblemMark on={badIn(bad, path, ["deployment_order"]) !== ""} /></summary>
        <div className={"row" + (bad(`${path}/deployment_order`) && !("custom" in team.deployment_order) ? " bad" : "")}>
          {planSelect(t("team.deployment_order"), orderSource, s.deployment_order_plans, (id) => set({
            deployment_order: id ? { plan: id } : { custom: [...(order ?? SINNERS)] },
          }))}
          {"custom" in team.deployment_order && <button type="button" onClick={saveOrderPlan}>{t("saveAsPlan")}</button>}
        </div>
        {"custom" in team.deployment_order ? (
          <SinnerGrid order={team.deployment_order.custom} path={`${path}/deployment_order/custom`}
            onChange={(custom) => set({ deployment_order: { custom } })} />
        ) : order && <>
          <p className="muted from-plan">{fill(t("team.fromPlan"), { tab: t("tab.deployment") })}</p>
          <SinnerGrid order={order} path={`${path}/deployment_order`} />
        </>}
      </details>

      <details className="panel" open data-sec="starlight">
        <summary className={badIn(bad, path, ["starlight"])}>{t("team.starlight")}<Holds>{starSource ? listName(starSource, s.starlight_plans, t("defaultPlan")) : t("custom")}{star && ` · ★ ${starlightCost(star.levels)}`}</Holds><ProblemMark on={badIn(bad, path, ["starlight"]) !== ""} /></summary>
        <div className={"row" + (bad(`${path}/starlight`) && !("custom" in team.starlight) ? " bad" : "")}>
          {planSelect(t("team.starlight"), starSource, s.starlight_plans, (id) => set({
            starlight: id ? { plan: id } : {
              custom: starPlan ? { levels: [...starPlan.levels], priority: [...starPlan.priority], convert_leftover: starPlan.convert_leftover } : defaultStarlight(),
            },
          }))}
          {"custom" in team.starlight && <button type="button" onClick={saveStarPlan}>{t("saveAsPlan")}</button>}
        </div>
        {"custom" in team.starlight ? (
          <StarlightEditor value={team.starlight.custom} path={`${path}/starlight/custom`}
            onChange={(custom) => set({ starlight: { custom } })} />
        ) : starPlan && <>
          <p className="muted from-plan">{fill(t("team.fromPlan"), { tab: t("tab.starlight") })}</p>
          <StarlightEditor value={starPlan} path={`${path}/starlight`} />
        </>}
      </details>

      <GiftSearchPanel i={i} />
      <KeepPanel i={i} />
      <SkillPanel i={i} />

      <details className="panel" open data-sec="more">
        <summary className={badIn(bad, path, MORE)}>{t("team.more")}<ProblemMark on={badIn(bad, path, MORE) !== ""} /></summary>
        <div className="rows">
          <div className={"toggle" + (bad(`${path}/guard_turns`) ? " bad" : "")}>
            <label className="check">
              <input type="checkbox" checked={team.guard_turns > 0} onChange={(e) => set({ guard_turns: e.target.checked ? 1 : 0 })} />
              {t("team.guard_turns")}
            </label>
            <select aria-label={t("team.guard_turns")} value={team.guard_turns || 1} disabled={!team.guard_turns} onChange={(e) => set({ guard_turns: Number(e.target.value) })}>
              {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{n} {t("team.turns")}</option>)}
            </select>
            <small>{t("team.guard_turns_note")}</small>
          </div>
          <ToggleNum label={t("team.hard_from_floor")} path={`${path}/hard_from_floor`} value={team.hard_from_floor} on={1} min={1} max={5}
            note={t("team.hard_from_floor_note")} onChange={(v) => set({ hard_from_floor: v })} />
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
            <select aria-label={t("team.usage")} value={team.usage === "any" ? "hard_only" : team.usage} disabled={team.usage === "any"}
              onChange={(e) => set({ usage: e.target.value })}>
              {teamEnum("usage").filter((u) => u !== "any").map((u) => <option key={u} value={u}>{tv("usage", u)}</option>)}
            </select>
          </div>
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
        <div className={"rewards" + (bad(`${path}/reward_cards`) ? " bad" : "")}>
          <h3>{t("team.reward_cards")}</h3>
          <ReorderList numbered items={team.reward_cards} keyOf={(x) => x} onChange={(reward_cards) => set({ reward_cards })}
            render={(x) => x} />
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
  return (
    <div className="gift-search">
      <div className="gift-tabs" role="tablist">
        {SEARCH_TABS.map((k) => (
          <button type="button" key={k} role="tab" data-tab={k} aria-selected={k === tab} tabIndex={k === tab ? 0 : -1}
            onKeyDown={tabKeys(SEARCH_TABS, tab, setTab)} className={k === tab ? "selected" : ""} onClick={() => setTab(k)}>
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

/** What the shop may sell (spec 04 section 9): the highest tier and the vestiges. What it buys, keeps and fuses is the team's
 * gift list (spec 04 section 13). */
function KeepPanel({ i }: { i: number }) {
  const { s, update, t, bad } = useEditor();
  const team = s.teams[i];
  const path = `teams/${i}`;
  const set = (patch: Partial<Team>) => update((d) => { Object.assign(d.teams[i], patch); });
  return (
    <details className="panel" data-sec="keep">
      {/* The summary, not the details: `.bad input` would outline every field of the panel (as in SkillPanel). */}
      <summary className={badIn(bad, path, ["sell_max_tier", "sell_vestiges"])}>{t("keep.title")}<Holds>≤ {TIERS[team.sell_max_tier]}</Holds><ProblemMark on={badIn(bad, path, ["sell_max_tier", "sell_vestiges"]) !== ""} /></summary>
      <p className="muted">{t("keep.note")}</p>
      <div className="rows">
        <div className={"toggle" + (bad(`${path}/sell_max_tier`) ? " bad" : "")}>
          <label htmlFor={`sell-max-${i}`}>{t("keep.sell_max_tier")}</label>
          <select id={`sell-max-${i}`} value={team.sell_max_tier} onChange={(e) => set({ sell_max_tier: Number(e.target.value) })}>
            {[1, 2, 3, 4, 5].map((n) => <option key={n} value={n}>{TIERS[n]}</option>)}
          </select>
          <small>{t("keep.sell_max_tier_note")}</small>
        </div>
        <div className={"toggle" + (bad(`${path}/sell_vestiges`) ? " bad" : "")}>
          <label className="check">
            <input type="checkbox" checked={team.sell_vestiges} onChange={(e) => set({ sell_vestiges: e.target.checked })} />
            {t("keep.sell_vestiges")}
          </label>
          <small>{withBreaks(t("keep.sell_vestiges_note"))}</small>
        </div>
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
    <details className="panel" data-sec="gift">
      <summary className={bad(path) ? "bad" : ""}>{t("gift.title")}{search.enabled && search.gifts.length ? ` (${search.gifts.length})` : ""}<ProblemMark on={bad(path)} /></summary>
      <div className="toggle">
        <label className="check">
          <input type="checkbox" checked={search.enabled} onChange={(e) => set({ enabled: e.target.checked })} />{t("gift.enabled")}
        </label>
        <small className="caution">{t("gift.note")}</small>
      </div>
      <GiftGrid gifts={search.gifts} start={main ?? SEARCH_TABS[0]} full={full} mark={(g) => (rank(g) ? String(rank(g)) : null)}
        onToggle={(g) => set({ gifts: toggleGift(search.gifts, g) })} />
      <div className={"rewards" + (bad(`${path}/gifts`) ? " bad" : "")}>
        <h3>{t("gift.order")} ({search.gifts.length}/{MAX_GIFTS})</h3>
        {full && <p className="muted">{t("gift.full")}</p>}
        {search.gifts.length ? (
          <ReorderList numbered items={search.gifts} keyOf={(g) => `${g.keyword}|${g.tier}|${g.name}`} onChange={(gifts) => set({ gifts })}
            onRemove={(j) => set({ gifts: toggleGift(search.gifts, search.gifts[j]) })}
            render={(g) => <>{refName(g, zh)} <small className="muted">{g.keyword} {TIERS[g.tier]}</small></>} />
        ) : <p className="muted">{t("gift.none")}</p>}
      </div>
    </details>
  );
}

/** The fields of a team that 其他設定 edits. */
const MORE = ["guard_turns", "hard_from_floor", "allow_white_gossypium", "usage", "heal", "reserve_cost", "shop_refresh_keyword",
  "shop_refresh_normal", "min_alive", "reward_cards"];

/** "bad" when a check failed on any of these fields of the team at `path`: the panel's summary shows it while the panel is closed. */
const badIn = (bad: (path: string) => boolean, path: string, keys: readonly string[]) => (keys.some((k) => bad(`${path}/${k}`)) ? "bad" : "");

/** The team page's panels, top to bottom (their `data-sec`), the title each shows and the fields it holds. */
const SECTIONS = [
  ["lists", "team.lists", ["gift_list", "theme_pack_plan"]],
  ["deployment", "team.deployment_order", ["deployment_order"]],
  ["starlight", "team.starlight", ["starlight"]],
  ["gift", "gift.title", ["gift_search"]],
  ["keep", "keep.title", ["sell_max_tier", "sell_vestiges"]],
  ["skill", "skill.title", ["skill_replacement"]],
  ["more", "team.more", MORE],
] as const;

/** A panel summary's note of what the panel holds (a plan's name, ★ cost), quiet beside its title. */
const Holds = ({ children }: { children: ReactNode }) => <span className="holds">{children}</span>;

/** A named list's name by id ("default" is the read-only default), or "? id" when the list is gone. */
function listName(id: string, lists: { id: string; name: string }[], fallback: string) {
  return id === "default" ? fallback : lists.find((x) => x.id === id)?.name || `? ${id}`;
}

/** The data-sec of the team page's panel nearest the top of the scrolling tab, for the jump bar. */
function useInView(page: RefObject<HTMLDivElement | null>) {
  const [key, setKey] = useState<string>();
  useEffect(() => {
    const root = page.current?.closest("main");
    if (!root || typeof IntersectionObserver === "undefined") return;
    const panels = [...page.current!.querySelectorAll<HTMLElement>("details[data-sec]")];
    const seen = new Map<Element, boolean>();
    const io = new IntersectionObserver((entries) => {
      for (const e of entries) seen.set(e.target, e.isIntersecting);
      setKey(panels.find((el) => seen.get(el))?.dataset.sec);
    }, { root, rootMargin: "-48px 0px -55% 0px" }); // under the jump bar, in the top half
    panels.forEach((el) => io.observe(el));
    return () => io.disconnect();
  }, [page]);
  return key;
}

/** Open a team page's section and scroll it to the top, under the jump bar. */
function jumpTo(from: Element, key: string) {
  const panel = from.closest(".team")?.querySelector<HTMLDetailsElement>(`details[data-sec="${key}"]`);
  if (!panel) return;
  panel.open = true;
  const still = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  panel.scrollIntoView?.({ block: "start", behavior: still ? "auto" : "smooth" });
}

/** Keep a dangling plan id selectable so the select shows it instead of silently changing it. */
function missing(id: string | false, plans: { id: string }[]) {
  return id && !plans.some((p) => p.id === id) ? <option value={id}>? {id}</option> : null;
}
