// A team's skill replacement (#264, #454, spec 04 section 9): the shop's Replace <sinner>'s Skill and ID Skill Search. Per sinner, in
// priority order, the skills 1/2/3 to aim for (a deck of 6) and the swaps it may use, the first tried first.
import { useDragSort } from "./dragSort";
import { fill } from "./i18n";
import { SKILL_PAYMENTS, SKILL_SWAPS, skillCounts, type SkillPay, type SkillReplacement } from "./model";
import { useEditor } from "./ui";

const move = <T,>(list: T[], from: number, to: number) => {
  const next = [...list];
  next.splice(to, 0, ...next.splice(from, 1));
  return next;
};
/** A swap as the game words it: the skill it takes a card from and the one it gives. */
const swapName = (k: string) => `SKILL ${SKILL_SWAPS[k].from} → ${SKILL_SWAPS[k].to}`;

export function SkillPanel({ i }: { i: number }) {
  const { s, update, t, tv, bad } = useEditor();
  const sr = s.teams[i].skill_replacement;
  const path = `teams/${i}/skill_replacement`;
  const edit = (fn: (draft: SkillReplacement) => void) => update((d) => fn(d.teams[i].skill_replacement));
  const search = sr.id_skill_search;
  const changed = sr.sinners.filter((x) => !skillCounts(x.target).untouched).length;

  // Rows are dragged by their index, a swap by its key within its sinner's group: a swap cannot land on another sinner or a row.
  const dragItem = useDragSort((from, to, group) => edit((d) => {
    if (group === "sinners") d.sinners = move(d.sinners, Number(from), Number(to));
    else {
      const x = d.sinners[Number(group.slice("swaps:".length))];
      const swap = (key: string) => key.slice(key.indexOf(":") + 1); // the key is "<sinner index>:<swap>": unique on the whole page
      x.options = move(x.options, x.options.indexOf(swap(from)), x.options.indexOf(swap(to)));
    }
  }), () => true);

  const seen = new Map<string, number>();
  return (
    <details className={"panel" + (bad(path) ? " bad" : "")}>
      <summary>{t("skill.title")}{changed ? ` (${changed})` : ""}</summary>
      <p className="muted">{t("skill.note")}</p>
      <ol className="skill-sinners">
        {sr.sinners.map((x, j) => {
          const { total, untouched } = skillCounts(x.target);
          const n = seen.get(x.sinner) ?? 0;
          seen.set(x.sinner, n + 1);
          const rowPath = `${path}/sinners/${j}`;
          const missing = Object.keys(SKILL_SWAPS).filter((k) => !x.options.includes(k));
          return (
            <li key={n ? `${x.sinner}#${n}` : x.sinner} data-sinner={x.sinner} className={bad(rowPath) || total !== 6 ? "bad" : ""}
              {...dragItem(String(j), "sinners")}>
              <div className="skill-head">
                <span className="grip" aria-hidden>⋮⋮</span>
                <b className="skill-rank">{j + 1}</b>
                <span className="skill-name">{x.sinner}</span>
                {(["s1", "s2", "s3"] as const).map((k) => (
                  <label key={k} className={"skill-count" + (bad(`${rowPath}/target/${k}`) ? " bad" : "")}>
                    <span>{k.toUpperCase()}</span>
                    <input type="number" min={0} max={6} step={1} value={x.target[k]} aria-label={`${x.sinner} ${k.toUpperCase()}`}
                      onChange={(e) => {
                        const v = e.target.value === "" ? 0 : Math.trunc(Number(e.target.value));
                        edit((d) => { d.sinners[j].target[k] = v; });
                      }} />
                  </label>
                ))}
                {total !== 6
                  ? <span role="alert" className="skill-err">{fill(t("skill.total_bad"), { sinner: x.sinner, total })}</span>
                  : untouched && <small className="muted">{t("skill.untouched")}</small>}
                <span className="spacer" />
                <button type="button" className="icon" aria-label={`${t("up")} ${x.sinner}`} title={t("up")} disabled={j === 0}
                  onClick={() => edit((d) => { d.sinners = move(d.sinners, j, j - 1); })}>↑</button>
                <button type="button" className="icon" aria-label={`${t("down")} ${x.sinner}`} title={t("down")} disabled={j === sr.sinners.length - 1}
                  onClick={() => edit((d) => { d.sinners = move(d.sinners, j, j + 1); })}>↓</button>
              </div>
              <ol className={"skill-swaps" + (bad(`${rowPath}/options`) ? " bad" : "")} aria-label={t("skill.swaps")}>
                {x.options.map((k, o) => (
                  <li key={k} data-swap={k} {...dragItem(`${j}:${k}`, `swaps:${j}`)}>
                    <span className="grip" aria-hidden>⋮⋮</span>
                    <span>{o + 1}. {swapName(k)}</span>
                    <small className="muted">{fill(t("skill.shop_price"), { price: SKILL_SWAPS[k].shop })}</small>
                    <button type="button" className="icon" aria-label={`${t("up")} ${swapName(k)}`} title={t("up")} disabled={o === 0}
                      onClick={() => edit((d) => { d.sinners[j].options = move(d.sinners[j].options, o, o - 1); })}>↑</button>
                    <button type="button" className="icon" aria-label={`${t("down")} ${swapName(k)}`} title={t("down")} disabled={o === x.options.length - 1}
                      onClick={() => edit((d) => { d.sinners[j].options = move(d.sinners[j].options, o, o + 1); })}>↓</button>
                    <button type="button" className="icon" aria-label={t("skill.remove_swap")} title={t("skill.remove_swap")} disabled={x.options.length === 1}
                      onClick={() => edit((d) => { d.sinners[j].options.splice(o, 1); })}>×</button>
                  </li>
                ))}
                {missing.map((k) => (
                  <li key={k} className="skill-add">
                    <button type="button" aria-label={`${t("skill.add_swap")} ${swapName(k)}`}
                      onClick={() => edit((d) => { d.sinners[j].options.push(k); })}>+ {swapName(k)}</button>
                  </li>
                ))}
              </ol>
            </li>
          );
        })}
      </ol>
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
        <small>{search.pay === "starlight" ? t("skill.pay_starlight_note") : t("skill.pay_cost_note")}</small>
        <small data-testid="id-search-prices">
          {t("skill.id_prices")} {Object.entries(SKILL_SWAPS).map(([k, v]) => `${swapName(k)} ${v.id_search[search.pay]}`).join("、")}{" "}
          {t(search.pay === "starlight" ? "skill.starlight" : "skill.cost")}
        </small>
      </div>
    </details>
  );
}
