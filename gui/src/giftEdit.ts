// Editing a gift list from the gift list tab: what applying a state does, and the context its components share.
import { createContext, useContext } from "react";
import { GIFT_BY_ID, wantable } from "./giftCatalog";
import { DEFAULT_LIST, lockers, type GiftState, type ListRules } from "./gifts";
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
}
export const GiftEditContext = createContext<GiftEdit>(null!);
export const useGiftEdit = () => useContext(GiftEditContext);

/** Give a list (a draft in the settings) the default list's content; its id and name stay. */
export function resetToDefault(list: GiftList) {
  const { order, want, keep, gorder, fusion_condition } = structuredClone(DEFAULT_LIST);
  Object.assign(list, { order, want, keep, gorder, fusion_condition });
}
