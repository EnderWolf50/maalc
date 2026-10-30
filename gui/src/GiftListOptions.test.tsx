// Component tests of the list options menu on the gift list tab (#308): what each option writes into the settings.
import { screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";
import { GiftListsTab } from "./GiftLists";
import { DEFAULT_LIST } from "./gifts";
import { TEXT } from "./i18n";
import { GIFT_KEYWORDS, SEARCH_GIFTS, defaultGorder, exportGiftList, newSettings, newTeam, type GiftList } from "./model";
import { renderEditor } from "./testing";
import { validate } from "./validate";

const zh = TEXT.zh_tw;
const say = (s: string, vars: Record<string, string | number> = {}) => s.replace(/\{(\w+)\}/g, (_, k) => String(vars[k]));
const mine = (patch: Partial<GiftList> = {}): GiftList => ({
  id: "mine", name: "Mine", order: [...GIFT_KEYWORDS], want: [], keep: [], gorder: defaultGorder(), fusion_condition: "any", ...patch,
});

async function open(lists: GiftList[], select = lists[0]?.id ?? "default", teams = newSettings().teams) {
  const r = renderEditor(<GiftListsTab />, { ...newSettings(), language: "zh_tw", gift_lists: lists, teams });
  if (select !== "default") await r.user.selectOptions(screen.getByRole("combobox", { name: zh["gl.list"] }), select);
  const menu = async () => { await r.user.click(screen.getByRole("button", { name: new RegExp("^" + zh["gl.opts"]) })); };
  const item = async (key: "rename" | "copy" | "blank" | "reset" | "export" | "import" | "delete") => {
    await menu();
    await r.user.click(screen.getByRole("menuitem", { name: new RegExp("^" + zh[`gl.opt_${key}`]) }));
  };
  return { ...r, menu, item };
}
const status = () => screen.getByRole("status").textContent;
const chosenName = () => (screen.getByRole("combobox", { name: zh["gl.list"] }) as HTMLSelectElement).selectedOptions[0].textContent;

describe("rename", () => {
  test("writes the new name; an empty or taken name is refused", async () => {
    const r = await open([mine({ want: [1] }), mine({ id: "other", name: "Other" })]);
    await r.item("rename");
    const box = screen.getByRole("textbox", { name: zh["gl.opt_rename"] });
    await r.user.clear(box);
    await r.user.click(screen.getByRole("button", { name: zh["gl.ok"] }));
    expect(screen.getByRole("alert").textContent).toBe(zh["gl.name_empty"]);
    await r.user.type(box, "Other");
    await r.user.click(screen.getByRole("button", { name: zh["gl.ok"] }));
    expect(screen.getByRole("alert").textContent).toBe(zh["gl.name_taken"]);
    expect(r.settings().gift_lists[0].name).toBe("Mine");
    await r.user.clear(box);
    await r.user.type(box, "Burn run");
    await r.user.click(screen.getByRole("button", { name: zh["gl.ok"] }));
    expect(r.settings().gift_lists[0]).toMatchObject({ name: "Burn run", want: [1] });
    expect(status()).toBe(say(zh["gl.renamed"], { name: "Burn run" }));
  });
});

describe("copy and new", () => {
  test("copy adds 'X 副本' with the same content and switches to it", async () => {
    const r = await open([mine({ want: [1], keep: [2] })]);
    await r.item("copy");
    const lists = r.settings().gift_lists;
    expect(lists).toHaveLength(2);
    expect(lists[1]).toMatchObject({ name: say(zh["gl.copy_name"], { name: "Mine" }), want: [1], keep: [2] });
    expect(lists[1].id).not.toBe("mine");
    expect(chosenName()).toBe(lists[1].name);
  });

  test("copying the read-only default makes an editable list with its content", async () => {
    const r = await open([], "default");
    await r.item("copy");
    const [copy] = r.settings().gift_lists;
    expect(copy).toMatchObject({ name: say(zh["gl.copy_name"], { name: zh["gl.default_name"] }), want: DEFAULT_LIST.want, keep: DEFAULT_LIST.keep });
    expect(screen.queryByText(zh["gl.readonly"])).toBeNull();
  });

  test("new adds an empty list and switches to it", async () => {
    const r = await open([mine({ want: [1] })]);
    await r.item("blank");
    const lists = r.settings().gift_lists;
    expect(lists[1]).toMatchObject({ name: zh["gl.blank_name"], want: [], fusion_condition: "any" });
    expect(chosenName()).toBe(zh["gl.blank_name"]);
  });

  test("new wants and keeps nothing, so every gift is Drop; copy the default to start from it (user decision 2026-10-30)", async () => {
    const r = await open([mine({ want: [1] })]);
    await r.item("blank");
    expect(r.settings().gift_lists[1]).toMatchObject({ want: [], keep: [] });
    expect(validate(r.settings())).toEqual([]);
    expect(screen.getByText(zh["gl.blank_made"].replace("{name}", zh["gl.blank_name"]))).toBeTruthy();
  });
});

describe("reset", () => {
  test("asks first; confirming copies the default's content over the list, keeping its name", async () => {
    const r = await open([mine({ want: [1], fusion_condition: "tier4" })]);
    await r.item("reset");
    expect(r.settings().gift_lists[0].want).toEqual([1]);
    await r.user.click(screen.getByRole("button", { name: zh["gl.ok"] }));
    expect(r.settings().gift_lists[0]).toMatchObject({
      id: "mine", name: "Mine", want: DEFAULT_LIST.want, keep: DEFAULT_LIST.keep, fusion_condition: DEFAULT_LIST.fusion_condition,
    });
  });

  test("backing out leaves the list alone", async () => {
    const r = await open([mine({ want: [1] })]);
    await r.item("reset");
    await r.user.click(screen.getByRole("button", { name: zh["gl.back"] }));
    expect(r.settings().gift_lists[0].want).toEqual([1]);
  });
});

describe("export and import", () => {
  test("export shows the list without its id and can copy it", async () => {
    const list = mine({ want: [1], keep: [2] });
    const r = await open([list]);
    await r.item("export");
    expect((screen.getByRole("textbox", { name: zh["gl.opt_export"] }) as HTMLTextAreaElement).value).toBe(exportGiftList(list));
    await r.user.click(screen.getByRole("button", { name: zh["gl.copy_text"] }));
    expect(await navigator.clipboard.readText()).toBe(exportGiftList(list));
  });

  test("import makes a new list named '(匯入)', says how many bad ids it skipped, and switches to it", async () => {
    const r = await open([mine()]);
    await r.item("import");
    const [a, b] = SEARCH_GIFTS.map((g) => g.id), text = JSON.stringify({ name: "Friend", want: [a, 999999], keep: [b] });
    await r.user.click(screen.getByRole("textbox", { name: zh["gl.opt_import"] }));
    await r.user.paste(text);
    await r.user.click(screen.getByRole("button", { name: zh["gl.import_ok"] }));
    const made = r.settings().gift_lists[1];
    expect(made).toMatchObject({ name: "Friend" + zh["gl.imported_suffix"], want: [a], keep: [b] });
    expect(chosenName()).toBe(made.name);
    expect(status()).toBe(say(zh["gl.imported_skipped"], { name: made.name, n: 1 }));
  });

  test("text that is not a gift list shows an error below the box and adds nothing", async () => {
    const r = await open([mine()]);
    await r.item("import");
    await r.user.click(screen.getByRole("textbox", { name: zh["gl.opt_import"] }));
    await r.user.paste("not json");
    await r.user.click(screen.getByRole("button", { name: zh["gl.import_ok"] }));
    expect(screen.getByRole("alert").textContent).toBe(zh["gl.import_bad"]);
    expect(r.settings().gift_lists).toHaveLength(1);
  });
});

describe("delete", () => {
  test("asks first; confirming removes the list and falls back to the default", async () => {
    const r = await open([mine(), mine({ id: "b", name: "B" })]);
    await r.item("delete");
    expect(r.settings().gift_lists).toHaveLength(2);
    await r.user.click(screen.getByRole("button", { name: zh["gl.ok"] }));
    expect(r.settings().gift_lists.map((l) => l.id)).toEqual(["b"]);
    expect(chosenName()).toBe(zh.defaultPlanLocked);
  });

  test("deleting a list a team uses leaves the cross-object check to fail on save", async () => {
    const team = { ...newTeam(1, "T"), gift_list: "mine" } as ReturnType<typeof newSettings>["teams"][number];
    const r = await open([mine()], "mine", [team]);
    await r.item("delete");
    await r.user.click(screen.getByRole("button", { name: zh["gl.ok"] }));
    expect(validate(r.settings()).map((p) => p.text).join("\n")).toContain("uses missing plan 'mine'");
  });
});

describe("the menu", () => {
  test("tabbing out of the open menu to the purchase order button and pressing Enter closes it", async () => {
    const r = await open([mine()]);
    await r.menu();
    expect(screen.getByRole("menu")).toBeInTheDocument();
    const buy = screen.getByRole("button", { name: /^購買排序/ });
    await r.user.tab();
    expect(screen.getByRole("menu")).toBeInTheDocument(); // focus moved inside the menu: it stays
    for (let i = 0; i < 20 && document.activeElement !== buy; i++) await r.user.tab(); // 20 only caps the walk
    expect(buy).toHaveFocus();
    await r.user.keyboard("{Enter}");
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.queryByRole("menu")).not.toBeInTheDocument();
  });
});

describe("the read-only default", () => {
  test("rename, reset and delete are disabled; copy, new, export and import work", async () => {
    const r = await open([], "default");
    await r.menu();
    for (const key of ["rename", "reset", "delete"] as const)
      expect(screen.getByRole("menuitem", { name: new RegExp("^" + zh[`gl.opt_${key}`]) })).toBeDisabled();
    for (const key of ["copy", "blank", "export", "import"] as const)
      expect(screen.getByRole("menuitem", { name: new RegExp("^" + zh[`gl.opt_${key}`]) })).toBeEnabled();
  });
});
