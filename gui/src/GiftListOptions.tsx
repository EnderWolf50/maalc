// The "list options" menu of the gift list tab (spec 04 section 13; #308): rename, copy, new, reset, export, import, delete.
// The read-only default cannot be renamed, reset or deleted. Delete just deletes: a team that still uses the list is caught by
// the cross-object check on save (validate.ts), as with the other plans.
import { useEffect, useRef, useState } from "react";
import { resetToDefault } from "./giftEdit";
import { DEFAULT_LIST } from "./gifts";
import { fill } from "./i18n";
import { GIFT_KEYWORDS, defaultGorder, exportGiftList, freeName, importGiftList, keywordlessIds, newId, type GiftList } from "./model";
import { useEditor } from "./ui";

type View = "menu" | "rename" | "reset" | "export" | "import" | "delete";

export function GiftListOptions({ at, readOnly, choose, flash }: {
  /** Index of the list being edited in the settings; -1 for the read-only default. */
  at: number; readOnly: boolean; choose: (id: string) => void; flash: (text: string, warn?: boolean) => void;
}) {
  const { s, update, t } = useEditor();
  const [view, setView] = useState<View | null>(null);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const box = useRef<HTMLSpanElement>(null);
  const current = readOnly ? null : s.gift_lists[at];
  const name = current?.name ?? t("gl.default_name");
  const names = s.gift_lists.map((l) => l.name);

  const show = (v: View | null, initial = "") => { setView(v); setText(initial); setError(""); };
  // Esc, a click outside, or focus moving outside (Tab to another control) closes it.
  useEffect(() => {
    if (!view) return;
    const out = (e: Event) => { if (!box.current?.contains(e.target as Node)) setView(null); };
    const esc = (e: KeyboardEvent) => { if (e.key === "Escape") setView(null); };
    document.addEventListener("mousedown", out);
    document.addEventListener("focusin", out);
    document.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", out); document.removeEventListener("focusin", out); document.removeEventListener("keydown", esc); };
  }, [view]);

  const add = (list: GiftList, message: "gl.copied_list" | "gl.blank_made" | "gl.imported") => {
    update((d) => { d.gift_lists.push(list); });
    choose(list.id);
    flash(fill(t(message), { name: list.name }));
    show(null);
  };
  const copy = () => {
    const base = structuredClone(current ?? DEFAULT_LIST);
    add({ ...base, id: newId(), name: freeName(fill(t("gl.copy_name"), { name }), names) }, "gl.copied_list");
  };
  const blank = () => add({
    id: newId(), name: freeName(t("gl.blank_name"), names), order: [...GIFT_KEYWORDS], want: [], keep: keywordlessIds(), gorder: defaultGorder(), fusion_condition: "any",
  }, "gl.blank_made");
  const rename = () => {
    const v = text.trim();
    if (!v) return setError(t("gl.name_empty"));
    if (names.some((n, i) => n === v && i !== at)) return setError(t("gl.name_taken"));
    update((d) => { d.gift_lists[at].name = v; });
    flash(fill(t("gl.renamed"), { name: v }));
    show(null);
  };
  const reset = () => {
    update((d) => resetToDefault(d.gift_lists[at]));
    flash(fill(t("gl.reset_done"), { name }));
    show(null);
  };
  const remove = () => {
    update((d) => { d.gift_lists.splice(at, 1); });
    choose("default"); // the tab falls back to the default once its list is gone; say so in the select too
    flash(fill(t("gl.deleted"), { name }));
    show(null);
  };
  const doImport = () => {
    try {
      const { list, skipped } = importGiftList(text, names, t("gl.imported_suffix"));
      add(list, "gl.imported");
      if (skipped) flash(fill(t("gl.imported_skipped"), { name: list.name, n: skipped }), true);
    } catch {
      setError(t("gl.import_bad"));
    }
  };
  const exported = current ? exportGiftList(current) : exportGiftList({ id: "default", name, ...DEFAULT_LIST });
  const copyText = async () => {
    try { await navigator.clipboard.writeText(exported); flash(t("gl.copied_text")); } catch { flash(t("gl.copy_failed"), true); }
  };

  const back = <button type="button" onClick={() => show("menu")}>{t("gl.back")}</button>;
  const item = (v: View | "copy" | "blank", label: string, off = false) => (
    <button type="button" role="menuitem" disabled={off} onClick={() => (v === "copy" ? copy() : v === "blank" ? blank() : show(v, v === "rename" ? name : ""))}>{label}</button>
  );
  const confirm = (ask: string, go: () => void) => (
    <div className="gl-opt-body"><p>{fill(ask, { name })}</p><div className="gl-opt-row"><button type="button" className="gl-opt-pri" onClick={go}>{t("gl.ok")}</button>{back}</div></div>
  );
  return (
    <span className="gl-opts" ref={box}>
      <button type="button" aria-haspopup="menu" aria-expanded={view !== null} onClick={() => (view ? setView(null) : show("menu"))}>{t("gl.opts")}</button>
      {view && (
        <div className="gl-opt-pop">
          <div className="gl-opt-head"><b>{fill(t("gl.opts_title"), { name })}</b></div>
          {view === "menu" && (
            <div role="menu" className="gl-opt-menu">
              {item("rename", t("gl.opt_rename"), readOnly)}
              {item("copy", t("gl.opt_copy"))}
              {item("blank", t("gl.opt_blank"))}
              {item("reset", t("gl.opt_reset"), readOnly)}
              {item("export", t("gl.opt_export") + "…")}
              {item("import", t("gl.opt_import") + "…")}
              {item("delete", t("gl.opt_delete"), readOnly)}
              {readOnly && <p className="gl-opt-note">{t("gl.opt_ro_note")}</p>}
            </div>
          )}
          {view === "rename" && (
            <div className="gl-opt-body">
              <input aria-label={t("gl.opt_rename")} value={text} maxLength={24} autoFocus onChange={(e) => setText(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && rename()} />
              {error && <div className="gl-opt-err" role="alert">{error}</div>}
              <div className="gl-opt-row"><button type="button" className="gl-opt-pri" onClick={rename}>{t("gl.ok")}</button>{back}</div>
            </div>
          )}
          {view === "reset" && confirm(t("gl.reset_ask"), reset)}
          {view === "delete" && confirm(t("gl.delete_ask"), remove)}
          {view === "export" && (
            <div className="gl-opt-body">
              <p>{t("gl.export_note")}</p>
              <textarea aria-label={t("gl.opt_export")} readOnly rows={5} value={exported} />
              <div className="gl-opt-row"><button type="button" className="gl-opt-pri" onClick={copyText}>{t("gl.copy_text")}</button>{back}</div>
            </div>
          )}
          {view === "import" && (
            <div className="gl-opt-body">
              <p>{t("gl.import_note")}</p>
              <textarea aria-label={t("gl.opt_import")} rows={5} value={text} onChange={(e) => { setText(e.target.value); setError(""); }} />
              {error && <div className="gl-opt-err" role="alert">{error}</div>}
              <div className="gl-opt-row"><button type="button" className="gl-opt-pri" onClick={doImport}>{t("gl.import_ok")}</button>{back}</div>
            </div>
          )}
        </div>
      )}
    </span>
  );
}
