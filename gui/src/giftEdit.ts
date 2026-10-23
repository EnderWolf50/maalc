// Editing a gift list from the gift list tab: what applying a state does, and the context its components share.
import { createContext, useContext } from "react";
import { GIFT_BY_ID, wantable } from "./giftCatalog";
import { DEFAULT_LIST, lockers, queue, type GiftState, type ListRules } from "./gifts";
import type { GiftList } from "./model";

/** What a click with this state does to a gift: refused because wanted fusions lock it, set to `to`, or set to keep because
 * it cannot be wanted. The GUI does not know the run's theme packs, so a pack-specific fusion always locks (lockers' null). */
export type Applied = { locked: number[] } | { to: GiftState; downgraded?: true };
export function plan(list: ListRules, id: number, to: GiftState): Applied {
  const locked = lockers(list, id);
  if (locked.length) return { locked };
  return to === "want" && !wantable(GIFT_BY_ID.get(id)!) ? { to: "keep", downgraded: true } : { to };
}

/** Write the state into a list (a draft in the settings): the gift leaves want and keep, then joins the one it is set to. */
export function setState(list: GiftList, id: number, to: GiftState) {
  list.want = list.want.filter((x) => x !== id);
  list.keep = list.keep.filter((x) => x !== id);
  if (to !== "drop") list[to].push(id);
}

/** The gifts of one keyword in buy order: the ones the list wants and the shop sells. */
export const buyList = (list: ListRules, keyword: string) => queue({ ...list, order: [keyword] });

/** Move keyword `from` to where keyword `to` is in `order`. */
export function moveKeyword(list: GiftList, from: string, to: string) {
  const at = list.order.indexOf(to);
  list.order.splice(list.order.indexOf(from), 1);
  list.order.splice(at, 0, from);
}

/** Move a gift of `gorder` onto the place of another of the same keyword: before it when moving up, after it when moving down. */
export function moveGift(list: GiftList, id: number, onto: number) {
  const g = list.gorder[GIFT_BY_ID.get(id)!.keyword], down = g.indexOf(id) < g.indexOf(onto);
  g.splice(g.indexOf(id), 1);
  g.splice(g.indexOf(onto) + (down ? 1 : 0), 0, id);
}

/** Move a gift past its neighbour in the buy list (`dir` -1 earlier, 1 later); gifts the list does not buy do not count. */
export function nudgeGift(list: GiftList, id: number, dir: -1 | 1) {
  const buy = buyList(list, GIFT_BY_ID.get(id)!.keyword), next = buy[buy.indexOf(id) + dir];
  if (next !== undefined) moveGift(list, id, next);
}

/** What the tab hands its parts: the list being shown, whether it can change, the state a click applies. */
export interface GiftEdit {
  list: ListRules;
  readOnly: boolean;
  /** The state a click applies (the apply bar's choice). */
  pick: GiftState;
  /** Apply a state to a gift (default: the picked one), or say why not. */
  apply: (id: number, to?: GiftState) => void;
  /** Show a line in the status area under the apply bar. */
  flash: (message: string, warn?: boolean) => void;
  /** True when the list can change; otherwise shows the read-only notice. */
  editable: () => boolean;
  /** Change the list being shown; false (with the read-only notice) when it cannot change. */
  change: (fn: (list: GiftList) => void) => boolean;
}
export const GiftEditContext = createContext<GiftEdit>(null!);
export const useGiftEdit = () => useContext(GiftEditContext);

/** Give a list (a draft in the settings) the default list's content; its id and name stay. */
export function resetToDefault(list: GiftList) {
  const { order, want, keep, gorder, fusion_condition } = structuredClone(DEFAULT_LIST);
  Object.assign(list, { order, want, keep, gorder, fusion_condition });
}
