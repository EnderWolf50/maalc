// A team's skill replacement (#264, #454, spec 04 section 9): the shop's Replace <sinner>'s Skill and ID Skill Search. Only the
// sinners to change are listed, in priority order (the layout the user adopted on 2026-11-06): S1 follows the S2 and S3 steppers,
// the row shows the swaps its target needs and, when it needs two kinds, which one to try first.
import { useDragSort } from "./dragSort";
import { fill } from "./i18n";
import {
  GAME_DECK, SINNERS, SKILL_PAYMENTS, SKILL_SWAPS, skillPlan, type SkillPay, type SkillReplacement, type SkillSwapKey, type SkillTarget,
} from "./model";
import { Grip, Holds, Icon, ProblemMark, useEditor, withBreaks } from "./ui";

const move = <T,>(list: T[], from: number, to: number) => {
  const next = [...list];
  next.splice(to, 0, ...next.splice(from, 1));
  return next;
};
const swapName = (k: SkillSwapKey) => `S${SKILL_SWAPS[k].from}→S${SKILL_SWAPS[k].to}`;
type Stepped = "s2" | "s3";
/** Which way a stepper may move a card between S1 and `k` and keep the target reachable: S1 0..3, S2 0 and up, S3 1 and up. */
const stepRoom = (t: SkillTarget, k: Stepped) => ({ dec: t[k] > (k === "s3" ? GAME_DECK.s3 : 0) && t.s1 < GAME_DECK.s1, inc: t.s1 > 0 });

export function SkillPanel({ i }: { i: number }) {
  const { s, update, t, tv, bad } = useEditor();
  const sr = s.teams[i].skill_replacement;
  const path = `teams/${i}/skill_replacement`;
  const edit = (fn: (draft: SkillReplacement) => void) => update((d) => fn(d.teams[i].skill_replacement));
  const search = sr.id_skill_search;
  const changed = sr.sinners.filter((x) => !skillPlan(x.target).untouched).length;
  const rest = SINNERS.filter((n) => !sr.sinners.some((x) => x.sinner === n));
  const dragItem = useDragSort((from, to) => edit((d) => { d.sinners = move(d.sinners, Number(from), Number(to)); }), () => true);

  const seen = new Map<string, number>(); // a hand-edited file can list a sinner twice (validate names it): keys stay unique
  return (
    <details className="panel skill-panel" data-sec="skill">
      <summary className={bad(path) ? "bad" : ""}>{t("skill.title")}{changed > 0 && <Holds>{changed}</Holds>}<ProblemMark on={bad(path)} /></summary>
      <p className="muted">{withBreaks(t("skill.note"))}</p>
      <select className="skill-add" aria-label={t("skill.add")} value="" disabled={!rest.length}
        onChange={(e) => { const sinner = e.target.value; edit((d) => { d.sinners.push({ sinner, target: { ...GAME_DECK }, s1_s3_first: true }); }); }}>
        <option value="">{t("skill.add")}</option>
        {rest.map((n) => <option key={n} value={n}>{n}</option>)}
      </select>
      {!sr.sinners.length && <p className="muted">{t("skill.empty")}</p>}
      <ol className="skill-sinners">
        {sr.sinners.map((x, j) => {
          const plan = skillPlan(x.target), target = x.target, faulty = plan.faults.length > 0;
          const needsTwo = plan.need.length > 1;
          const otherSwap = plan.need.find((v) => v.key !== "s1_s3")?.key;
          const n = seen.get(x.sinner) ?? 0;
          seen.set(x.sinner, n + 1);
          const rowPath = `${path}/sinners/${j}`;
          // a step moves one card between S1 and `k`, so the deck stays 6
          const shift = (k: Stepped, d: 1 | -1) => edit((draft) => { const goal = draft.sinners[j].target; goal.s1 -= d; goal[k] += d; });
          return (
            <li key={n ? `${x.sinner}#${n}` : x.sinner} data-sinner={x.sinner} className={bad(rowPath) || faulty ? "faulty" : ""}
              {...dragItem(String(j), "sinners")}>
              <Grip />
              <b className="skill-rank">{j + 1}</b>
              <span className="skill-name" title={x.sinner}>{x.sinner}</span>
              <span className="skill-count">
                <span>S1</span>
                <span className="skill-box ro" aria-label={`${x.sinner} S1`} title={t("skill.s1_auto")}>{target.s1}</span>
              </span>
              {(["s2", "s3"] as const).map((k) => {
                const name = `${x.sinner} ${k.toUpperCase()}`, ok = stepRoom(target, k);
                return (
                  <span key={k} className="skill-count">
                    <span>{k.toUpperCase()}</span>
                    <span className="skill-box skill-spin" role="group" aria-label={name}>
                      <button type="button" aria-label={`${name} ${t("skill.dec")}`} disabled={faulty || !ok.dec} onClick={() => shift(k, -1)}>−</button>
                      <span className="n" aria-live="polite">{target[k]}</span>
                      <button type="button" aria-label={`${name} ${t("skill.inc")}`} disabled={faulty || !ok.inc} onClick={() => shift(k, 1)}>+</button>
                    </span>
                  </span>
                );
              })}
              <span className="skill-pillcell">
                {faulty
                  ? <span role="alert" className="skill-pill err">
                    {plan.faults.map((f) => fill(t(`skill.fault_${f}`), { total: target.s1 + target.s2 + target.s3 })).join(t("skill.sep"))}
                  </span>
                  : plan.untouched ? <span className="skill-pill off">{t("skill.unchanged")}</span>
                  : <span className="skill-pill on">{plan.need.map((v) => `${swapName(v.key)} ×${v.n}`).join(t("skill.sep"))}</span>}
              </span>
              <select className="skill-first" aria-label={`${x.sinner} ${t("skill.order")}`} disabled={!needsTwo}
                title={faulty ? undefined : needsTwo ? t("skill.order_two") : t("skill.order_one")}
                value={needsTwo ? (x.s1_s3_first ? "s1_s3" : otherSwap) : ""}
                onChange={(e) => edit((d) => { d.sinners[j].s1_s3_first = e.target.value === "s1_s3"; })}>
                {needsTwo && otherSwap
                  ? (["s1_s3", otherSwap] as const).map((k) => <option key={k} value={k}>{fill(t("skill.first"), { swap: swapName(k) })}</option>)
                  : <option value="">—</option>}
              </select>
              <span className="moves">
                <button type="button" className="icon" aria-label={`${t("up")} ${x.sinner}`} title={t("up")} disabled={j === 0}
                  onClick={() => edit((d) => { d.sinners = move(d.sinners, j, j - 1); })}><Icon name="up" /></button>
                <button type="button" className="icon" aria-label={`${t("down")} ${x.sinner}`} title={t("down")} disabled={j === sr.sinners.length - 1}
                  onClick={() => edit((d) => { d.sinners = move(d.sinners, j, j + 1); })}><Icon name="down" /></button>
                <button type="button" className="icon remove" aria-label={`${t("skill.remove")} ${x.sinner}`} title={t("skill.remove")}
                  onClick={() => edit((d) => { d.sinners.splice(j, 1); })}><Icon name="remove" /></button>
              </span>
            </li>
          );
        })}
      </ol>
      <p className="muted skill-rest">{t("skill.rest")}{rest.join(t("skill.sep")) || t("skill.rest_none")}</p>
      <p className="muted">{t("skill.uptie")}</p>
      <div className={"toggle" + (bad(`${path}/id_skill_search`) ? " bad" : "")}>
        <label className="check">
          <input type="checkbox" checked={search.enabled} onChange={(e) => edit((d) => { d.id_skill_search.enabled = e.target.checked; })} />
          {t("skill.id_search")}
        </label>
        <select aria-label={t("skill.pay")} value={search.pay} disabled={!search.enabled}
          onChange={(e) => edit((d) => { d.id_skill_search.pay = e.target.value as SkillPay; })}>
          {SKILL_PAYMENTS.map((v) => <option key={v} value={v}>{tv("skill_pay", v)}</option>)}
        </select>
        <small>{t("skill.id_search_note")}</small>
        {search.pay === "starlight"
          ? <small className="caution">{t("skill.pay_starlight_note")}</small>
          : <small>{t("skill.pay_cost_note")}</small>}
      </div>
    </details>
  );
}
