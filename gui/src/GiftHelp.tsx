// The "Help" popover of the gift list tab (#307): the legend of the tile frames, the keys and the purchase order rule.
import type { Key } from "./i18n";
import { useEditor } from "./ui";

const LEGEND: { swatch: string; name: Key; text: Key }[] = [
  { swatch: "want", name: "state.want", text: "gl.help_want" },
  { swatch: "keep", name: "state.keep", text: "gl.help_keep" },
  { swatch: "drop", name: "state.drop", text: "gl.help_drop" },
  { swatch: "locked", name: "gl.help_locked_name", text: "gl.help_locked" },
  { swatch: "fusion", name: "gl.help_fusion_name", text: "gl.help_fusion" },
];
// Keys and what they do; a key shown as "gl.k_space" is a word, not a symbol.
const KEYS: { keys: string[]; text: Key }[] = [
  { keys: ["/"], text: "gl.k_search" },
  { keys: ["1", "2", "3"], text: "gl.k_state" },
  { keys: ["←", "→"], text: "gl.k_move" },
  { keys: ["↑", "↓"], text: "gl.k_row" },
  { keys: ["Enter", "gl.k_space"], text: "gl.k_apply" },
  { keys: ["Esc"], text: "gl.k_esc" },
];

export function HelpPopover() {
  const { t } = useEditor();
  return (
    <div className="gl-pop" role="dialog" aria-label={t("gl.help")}>
      {LEGEND.map(({ swatch, name, text }) => (
        <div key={swatch} className="gl-lg">
          <i className={`gl-sw ${swatch}`} aria-hidden>{swatch === "fusion" ? "IV" : ""}</i>
          <b>{t(name)}</b><span>{t(text)}</span>
        </div>
      ))}
      <div className="gl-sech">{t("gl.help_ops")}</div>
      <p>{t("gl.help_keys")}</p>
      <ul className="gl-keys">
        {KEYS.map(({ keys, text }) => (
          <li key={text}>{keys.map((k) => <kbd key={k}>{k.startsWith("gl.") ? t(k as Key) : k}</kbd>)} {t(text)}</li>
        ))}
      </ul>
      <p className="gl-note">{t("gl.help_order")}</p>
    </div>
  );
}
