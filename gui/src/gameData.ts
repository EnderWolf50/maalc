// The game's data as the window shows it: read once when the module loads (top-level await, api.ts loadGameFiles) from
// <root>/resource/base/data, so the resource package's newer files show without a new build. When the data cannot be read the
// import rejects and main.tsx shows why. The `import type` lines take only the files' shapes; no data is bundled.
import type recipesFile from "../../assets/resource/base/data/gift_recipes.json";
import type searchFile from "../../assets/resource/base/data/gift_search.json";
import type effectsFile from "../../assets/resource/base/data/gift_effects.json";
import type gracesFile from "../../assets/resource/base/data/graces.json";
import { loadGameFiles } from "./api";

const files = await loadGameFiles();

const text = (name: string): string => files.texts[name] ?? "";
const json = <T>(name: string): T => JSON.parse(text(name)) as T;

export const recipes = json<typeof recipesFile>("gift_recipes.json");
export const search = json<typeof searchFile>("gift_search.json");
export const effects = json<typeof effectsFile>("gift_effects.json");
export const graces = json<typeof gracesFile>("graces.json");
/** data/shop.yaml, gift_lists.yaml and theme_packs.yaml as text: the callers parse them. */
export const shopYaml = text("shop.yaml");
export const giftListsYaml = text("gift_lists.yaml");
export const themePacksYaml = text("theme_packs.yaml");

/** The file names of an image folder under data/ and the URL of one: `folder/<name>`. */
export const imageNames = (folder: string): string[] => files.folders[folder] ?? [];
export const imageUrl = (path: string): string => files.url(path);

/** A folder of the game's art as WebP files: a key's URL, undefined for a key without a file. `index`: the folder's index.json
 * ({key: file}) when its files are named by an index (the sinner cards and theme pack covers); without one a key's file is
 * `<key>.webp`. */
export function webpFolder(folder: string, index?: string): (key: string | number) => string | undefined {
  const present = new Set(imageNames(folder));
  const names = index === undefined ? undefined : (JSON.parse(text(index)) as Record<string, string>);
  return (key) => {
    const name = names ? names[key] : `${key}.webp`;
    return name !== undefined && present.has(name) ? imageUrl(`${folder}/${name}`) : undefined;
  };
}

/** The stylesheet's art: the game's sprites it draws (index.css). Each name is a CSS variable, set on the page's root as
 * `url(...)`, because a stylesheet cannot name a file the build does not hold. */
const ART = ["sinner_frame/frame", "sinner_frame/glow", "sinner_frame/plate-deployed", "sinner_frame/plate-backup",
  "grace_card/page", "grace_card/face", "grace_card/face-picked", "grace_card/hover", "grace_card/star", "grace_card/button",
  "grace_card/button-lit", "grace_card/plus", "grace_card/plus-lit", "grace_card/side"];
/** The CSS variable of a sprite, `sinner_frame/frame` -> `--sprite-sinner-frame-frame`. */
export const artVar = (sprite: string) => "--sprite-" + sprite.replace(/[/_]/g, "-");
export function applyArt(root: HTMLElement = document.documentElement): void {
  for (const sprite of ART) root.style.setProperty(artVar(sprite), `url("${imageUrl(sprite + ".webp")}")`);
}
