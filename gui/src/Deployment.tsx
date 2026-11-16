// Deployment order (spec 04 section 6): the sinner grid, which the plans tab and a team's own order both edit.
import { SINNERS, toggleSinner, type DeploymentPlan, type Order } from "./model";
import { PlanTab } from "./Plans";
import { useEditor } from "./ui";
import { webpFolder } from "./gameData";

// #718's cards (sinner_cards/index.json: sinner -> file, each sinner's default identity); a sinner without one shows its frame
// alone. The name is printed on the tile, so the art is decoration.
const cardOf = webpFolder("sinner_cards", "sinner_cards/index.json");

/** The 12 sinners in the game's grid, each on its default identity's card; clicking adds one at the end of the order or
 * leaves it out (spec 04 section 6). As the formation screen does, a sinner in the order shows its card darkened and one left
 * out grey (index.css). Read-only without onChange. */
export function SinnerGrid({ order, onChange, path }: { order: Order; onChange?: (o: Order) => void; path: string }) {
  const { t, bad } = useEditor();
  return (<>
    {onChange && <p className="muted">{t("order.hint")}</p>}
    <div className={"sinners" + (onChange ? "" : " readonly") + (bad(path) ? " bad" : "")} data-path={path}>
      {SINNERS.map((s) => {
        const n = order.indexOf(s) + 1;
        const kind = n === 0 ? "out" : n <= 7 ? "deployed" : "backup";
        const art = cardOf(s);
        return (
          <button type="button" key={s} className={"sinner " + kind} disabled={!onChange} aria-pressed={n > 0}
            onClick={() => onChange?.(toggleSinner(order, s))}>
            {art && <img src={art} alt="" draggable={false} />}
            {n > 0 && <span className="num">{n}</span>}
            {n > 0 && <span className="banner">{t(n <= 7 ? "order.deployed" : "order.backup")}</span>}
            <span className="name">{s}</span>
          </button>
        );
      })}
    </div>
  </>);
}

export const DeploymentTab = () => (
  <PlanTab<DeploymentPlan> planKey="deployment_order_plans" tab="tab.deployment" make={() => ({ order: [...SINNERS] })}
    editor={(p, change, path) => <SinnerGrid order={p.order} path={`${path}/order`} onChange={(order) => change({ ...p, order })} />} />
);
