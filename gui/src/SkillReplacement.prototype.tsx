// PROTOTYPE for #264 UI feedback, throwaway branch proto/skill-replacement-ui, never merge
// Three variants of the 技能替換 panel, flipped with ?variant=A|B|C (or the floating bar / ← →). State is in memory only.
import { useState, useSyncExternalStore, type Dispatch, type SetStateAction } from "react";
import "./SkillReplacement.prototype.css";
import { useDragSort } from "./dragSort";
import { GAME_DECK, SKILL_PAYMENTS, SKILL_SWAPS, type SkillPay, type SkillReplacement, type SkillTarget } from "./model";
import { useEditor } from "./ui";

// ---------- shared pure helpers ----------
const KEYS = ["s1_s2", "s2_s3", "s1_s3"] as const;
const short = (k: string) => `${SKILL_SWAPS[k].from}→${SKILL_SWAPS[k].to}`;
const long = (k: string) => `S${SKILL_SWAPS[k].from}→S${SKILL_SWAPS[k].to}`;
const move = <T,>(list: T[], from: number, to: number) => {
  const next = [...list];
  next.splice(to, 0, ...next.splice(from, 1));
  return next;
};

export interface Plan {
  total: number; untouched: boolean; error: string | null;
  /** swaps the target needs, with how many times each */
  need: { key: string; n: number }[];
  times: number; cost: number;
}
/** What a target takes: the swaps (they only move a card up), their count and the Cost; or why it cannot be reached. */
export function plan(t: SkillTarget): Plan {
  const total = t.s1 + t.s2 + t.s3;
  const untouched = t.s1 === GAME_DECK.s1 && t.s2 === GAME_DECK.s2 && t.s3 === GAME_DECK.s3;
  const error = t.s1 < 0 || t.s2 < 0 || t.s3 < 0 ? "不能為負" : total !== 6 ? `合計 ${total}，要 6`
    : t.s1 > 3 ? "S1 不能超過 3" : t.s3 < 1 ? "S3 不能少於 1" : null;
  const counts: Record<string, number> = { s1_s2: 0, s2_s3: 0, s1_s3: 0 };
  if (!error) {
    if (t.s2 > 2) { counts.s1_s2 = t.s2 - 2; counts.s1_s3 = t.s3 - 1; }
    else { counts.s2_s3 = 2 - t.s2; counts.s1_s3 = 3 - t.s1; }
  }
  const need = KEYS.filter((k) => counts[k] > 0).map((key) => ({ key, n: counts[key] }));
  return {
    total, untouched, error, need,
    times: need.reduce((a, x) => a + x.n, 0), cost: need.reduce((a, x) => a + x.n * SKILL_SWAPS[x.key].shop, 0),
  };
}
const planText = (p: Plan) => p.need.map((x) => `${long(x.key)} ×${x.n}`).join("、");

interface Row { sinner: string; target: SkillTarget; order: string[] }
const seedRows = (sr: SkillReplacement): Row[] => sr.sinners.map((x) => ({
  sinner: x.sinner, target: { ...x.target },
  order: [...x.options, ...KEYS.filter((k) => !x.options.includes(k))],
}));
/** The swap tried first among the ones the target needs (only matters with two kinds). */
const firstOf = (r: Row, p: Plan) => r.order.find((k) => p.need.some((x) => x.key === k));
const withFirst = (r: Row, first: string): Row => ({ ...r, order: [first, ...r.order.filter((k) => k !== first)] });

type SetRows = Dispatch<SetStateAction<Row[]>>;
const patch = (set: SetRows, j: number, f: (r: Row) => Row) => set((rs) => rs.map((r, k) => (k === j ? f(r) : r)));

// ---------- the switcher ----------
const NAMES: Record<string, string> = { A: "A 下拉選順序", B: "B 點牌換技能", C: "C 換技能清單" };
const VARIANTS = Object.keys(NAMES);
let current = (() => {
  try { const v = new URLSearchParams(window.location.search).get("variant")?.toUpperCase() ?? "A"; return VARIANTS.includes(v) ? v : "A"; }
  catch { return "A"; }
})();
const listeners = new Set<() => void>();
function setVariant(v: string) {
  current = v;
  try { const u = new URL(window.location.href); u.searchParams.set("variant", v); window.history.replaceState(null, "", u); } catch { /* ignore */ }
  listeners.forEach((l) => l());
}
const cycle = (d: number) => setVariant(VARIANTS[(VARIANTS.indexOf(current) + d + VARIANTS.length) % VARIANTS.length]);
window.addEventListener("keydown", (e) => {
  const el = document.activeElement as HTMLElement | null;
  if (el && (/^(INPUT|SELECT|TEXTAREA)$/.test(el.tagName) || el.isContentEditable)) return;
  if (e.key === "ArrowLeft") cycle(-1);
  else if (e.key === "ArrowRight") cycle(1);
});
const useVariant = () => useSyncExternalStore((l) => { listeners.add(l); return () => { listeners.delete(l); }; }, () => current);

function Switcher({ v }: { v: string }) {
  return (
    <div className="sp-switcher" role="group" aria-label="原型切換">
      <button type="button" aria-label="上一個變體" onClick={() => cycle(-1)}>←</button>
      <b data-testid="sp-label">{NAMES[v]}</b>
      <button type="button" aria-label="下一個變體" onClick={() => cycle(1)}>→</button>
    </div>
  );
}

// ---------- today's ID Skill Search block, lifted unchanged ----------
function IdSearch({ i }: { i: number }) {
  const { s, update, t, tv, bad } = useEditor();
  const path = `teams/${i}/skill_replacement`;
  const search = s.teams[i].skill_replacement.id_skill_search;
  const edit = (fn: (draft: SkillReplacement) => void) => update((d) => fn(d.teams[i].skill_replacement));
  const swapName = (k: string) => `SKILL ${SKILL_SWAPS[k].from} → ${SKILL_SWAPS[k].to}`;
  return (
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
  );
}

// ---------- entry ----------
export function SkillPrototype({ i }: { i: number }) {
  const { s, t } = useEditor();
  const v = useVariant();
  const [seed] = useState(() => seedRows(s.teams[i].skill_replacement));
  const changed = seed.filter((r) => !plan(r.target).untouched).length;
  return (
    <details className="panel skill-panel sp">
      <summary>{t("skill.title")}{changed ? ` (${changed})` : ""}</summary>
      <p className="sp-banner">原型：這裡的修改不會儲存</p>
      {v === "A" && <VariantA key="A" seed={seed} />}
      {v === "B" && <VariantB key="B" seed={seed} />}
      {v === "C" && <VariantC key="C" seed={seed} />}
      <p className="muted sp-note">技能 3 需要 Uptie 3；沒有的身分只能用 1→2。（原型不模擬）</p>
      <IdSearch i={i} />
      <Switcher v={v} />
    </details>
  );
}

// ---------- shared small parts ----------
function Arrows({ j, n, set, name }: { j: number; n: number; set: SetRows; name: string }) {
  return (
    <span className="sp-arrows">
      <button type="button" className="icon" aria-label={`上移 ${name}`} disabled={j === 0} onClick={() => set((rs) => move(rs, j, j - 1))}>↑</button>
      <button type="button" className="icon" aria-label={`下移 ${name}`} disabled={j === n - 1} onClick={() => set((rs) => move(rs, j, j + 1))}>↓</button>
    </span>
  );
}
function Segmented({ p, r, onPick }: { p: Plan; r: Row; onPick: (k: string) => void }) {
  const first = firstOf(r, p);
  return (
    <span className="sp-seg" role="group" aria-label="先換">
      <span className="muted">先換：</span>
      {p.need.map((x) => (
        <button key={x.key} type="button" aria-pressed={x.key === first} className={x.key === first ? "on" : ""} onClick={() => onPick(x.key)}>
          {long(x.key)} <small>{SKILL_SWAPS[x.key].shop}</small>
        </button>
      ))}
    </span>
  );
}

// ---------- A: a select per sinner ----------
const PERMS = (() => {
  const out: string[][] = [];
  for (const a of KEYS) for (const b of KEYS) for (const c of KEYS) if (a !== b && b !== c && a !== c) out.push([a, b, c]);
  return out;
})();

function VariantA({ seed }: { seed: Row[] }) {
  const [rows, setRows] = useState(seed);
  const dragItem = useDragSort((from, to) => setRows((rs) => move(rs, Number(from), Number(to))), () => true);
  return (
    <ol className="sp-a">
      {rows.map((r, j) => {
        const p = plan(r.target);
        const quiet = p.untouched;
        const canOrder = !p.error && p.need.length > 1;
        return (
          <li key={r.sinner} className={quiet ? "quiet" : ""} data-sinner={r.sinner} {...dragItem(String(j), "rows")}>
            <span className="grip" aria-hidden>⋮⋮</span>
            <b className="skill-rank">{j + 1}</b>
            <span className="skill-name">{r.sinner}</span>
            {(["s1", "s2", "s3"] as const).map((k) => (
              <label key={k} className="skill-count">
                <span>{k.toUpperCase()}</span>
                <input type="number" min={0} max={6} step={1} value={r.target[k]} aria-label={`${r.sinner} ${k.toUpperCase()}`}
                  onChange={(e) => {
                    const val = e.target.value === "" ? 0 : Math.trunc(Number(e.target.value));
                    patch(setRows, j, (x) => ({ ...x, target: { ...x.target, [k]: val } }));
                  }} />
              </label>
            ))}
            <span className="sp-pillcell">
              {p.error ? <span className="sp-pill err" role="alert">{p.error}</span>
                : p.untouched ? <span className="sp-pill off">不換</span>
                : <span className="sp-pill on">換 {p.times} 次・{p.cost} Cost</span>}
            </span>
            <select className="sp-order" aria-label={`${r.sinner} 換法順序`} disabled={!canOrder}
              title={canOrder ? "兩種換法都要用時，先試哪一種" : p.untouched || p.error ? "" : "只需要一種換法，順序不影響"}
              value={canOrder ? r.order.join(",") : ""}
              onChange={(e) => patch(setRows, j, (x) => ({ ...x, order: e.target.value.split(",") }))}>
              {!canOrder && <option value="">—</option>}
              {PERMS.map((o) => <option key={o.join()} value={o.join(",")}>{o.map(short).join(" › ")}</option>)}
            </select>
            <Arrows j={j} n={rows.length} set={setRows} name={r.sinner} />
          </li>
        );
      })}
    </ol>
  );
}

// ---------- B: click a card to raise it ----------
function Pips({ r, onRaise }: { r: Row; onRaise: (v: 1 | 2) => void }) {
  const t = r.target;
  const cards = [...Array(Math.max(0, t.s1)).fill(1), ...Array(Math.max(0, t.s2)).fill(2), ...Array(Math.max(0, t.s3)).fill(3)] as number[];
  return (
    <span className="sp-pips" role="group" aria-label={`${r.sinner} 牌組`}>
      {cards.map((v, k) => (
        <button key={k} type="button" className={`sp-pip s${v}`} aria-label={v === 3 ? `技能 3` : `技能 ${v} 升到 ${v + 1}`} title={v === 3 ? "已是最高" : `點一下：技能 ${v} → 技能 ${v + 1}`}
          onClick={() => v < 3 && onRaise(v as 1 | 2)}>{v}</button>
      ))}
    </span>
  );
}

function VariantB({ seed }: { seed: Row[] }) {
  const [rows, setRows] = useState(seed);
  return (
    <ol className="sp-b">
      {rows.map((r, j) => {
        const p = plan(r.target);
        const raise = (v: 1 | 2) => patch(setRows, j, (x) => {
          const key = `s${v}` as "s1" | "s2", up = `s${v + 1}` as "s2" | "s3";
          return { ...x, target: { ...x.target, [key]: x.target[key] - 1, [up]: x.target[up] + 1 } };
        });
        return (
          <li key={r.sinner} className={p.untouched ? "quiet" : "changed"} data-sinner={r.sinner}>
            <div className="line1">
              <b className="skill-rank">{j + 1}</b>
              <span className="skill-name">{r.sinner}</span>
              <Pips r={r} onRaise={raise} />
              <span className="sp-counts muted">S1 {r.target.s1}・S2 {r.target.s2}・S3 {r.target.s3}</span>
              {!p.untouched && <button type="button" className="icon" aria-label={`重設 ${r.sinner}`} title="重設為 3/2/1"
                onClick={() => patch(setRows, j, (x) => ({ ...x, target: { ...GAME_DECK } }))}>↺</button>}
              <span className="spacer" />
              <Arrows j={j} n={rows.length} set={setRows} name={r.sinner} />
            </div>
            {!p.untouched && (
              <div className="line2">
                {p.error ? <span className="sp-pill err">{p.error}</span> : <>
                  <span>{planText(p)}・共 <b>{p.cost}</b> Cost</span>
                  {p.need.length > 1 && <Segmented p={p} r={r} onPick={(k) => patch(setRows, j, (x) => withFirst(x, k))} />}
                </>}
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

// ---------- C: only the sinners to change ----------
function Stepper({ label, value, dec, inc, decOff, incOff }: { label: string; value: number; dec: () => void; inc: () => void; decOff: boolean; incOff: boolean }) {
  return (
    <span className="sp-step">
      <span className="muted">{label}</span>
      <button type="button" aria-label={`${label} 減一`} disabled={decOff} onClick={dec}>−</button>
      <b>{value}</b>
      <button type="button" aria-label={`${label} 加一`} disabled={incOff} onClick={inc}>+</button>
    </span>
  );
}

function VariantC({ seed }: { seed: Row[] }) {
  const all = seed.map((r) => r.sinner);
  const [rows, setRows] = useState(() => seed.filter((r) => !plan(r.target).untouched));
  const rest = all.filter((n) => !rows.some((r) => r.sinner === n));
  const total = rows.reduce((a, r) => a + plan(r.target).cost, 0);
  const adjust = (j: number, k: "s2" | "s3", d: 1 | -1) => patch(setRows, j, (x) => {
    const t = { ...x.target };
    t[k] += d; t.s1 -= d;
    return { ...x, target: t };
  });
  return (
    <div className="sp-c">
      <div className="sp-add">
        <select aria-label="加入罪人" value="" disabled={!rest.length}
          onChange={(e) => { const n = e.target.value; const base = seed.find((r) => r.sinner === n); if (base) setRows((rs) => [...rs, { ...base, target: { ...GAME_DECK } }]); }}>
          <option value="">＋ 加入罪人</option>
          {rest.map((n) => <option key={n} value={n}>{n}</option>)}
        </select>
      </div>
      {!rows.length && <p className="muted sp-empty">目前沒有罪人要換技能，全部維持 3／2／1。</p>}
      <ol className="sp-cards">
        {rows.map((r, j) => {
          const p = plan(r.target), t = r.target;
          return (
            <li key={r.sinner} data-sinner={r.sinner}>
              <div className="head">
                <b className="skill-rank">{j + 1}</b>
                <span className="skill-name">{r.sinner}</span>
                <span className="spacer" />
                <Arrows j={j} n={rows.length} set={setRows} name={r.sinner} />
                <button type="button" className="icon" aria-label={`移除 ${r.sinner}，改回不換`} title="移除（改回 3/2/1，不換）"
                  onClick={() => setRows((rs) => rs.filter((_, k) => k !== j))}>✕</button>
              </div>
              <div className="steps">
                <span className="sp-step"><span className="muted">S1</span><b className="ro">{t.s1}</b></span>
                <Stepper label="S2" value={t.s2} decOff={t.s2 <= 0 || t.s1 >= 3} incOff={t.s1 <= 0} dec={() => adjust(j, "s2", -1)} inc={() => adjust(j, "s2", 1)} />
                <Stepper label="S3" value={t.s3} decOff={t.s3 <= 1 || t.s1 >= 3} incOff={t.s1 <= 0} dec={() => adjust(j, "s3", -1)} inc={() => adjust(j, "s3", 1)} />
              </div>
              <div className="plan">
                {p.untouched ? <span className="muted">還沒有變更（3／2／1）</span> : <span>{planText(p)}・共 <b>{p.cost}</b> Cost</span>}
              </div>
              {p.need.length > 1 && (
                <label className="first">先換
                  <select aria-label={`${r.sinner} 先換`} value={firstOf(r, p)} onChange={(e) => patch(setRows, j, (x) => withFirst(x, e.target.value))}>
                    {p.need.map((x) => <option key={x.key} value={x.key}>{long(x.key)}（{SKILL_SWAPS[x.key].shop}）</option>)}
                  </select>
                </label>
              )}
            </li>
          );
        })}
      </ol>
      <p className="muted sp-foot">不換：{rest.join("、") || "（無）"}</p>
      <p className="sp-foot"><b>全部換完共 {total} Cost</b></p>
    </div>
  );
}
