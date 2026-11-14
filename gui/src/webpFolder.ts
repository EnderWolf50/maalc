// A folder of the game's art as WebP files, bundled at build time: a key's URL. Each folder is read by its own
// import.meta.glob calls, whose patterns Vite needs as literals in the module that bundles them.

/** The URL of a key's file in a folder of WebP files, undefined for a key without one (also in a build before the folder
 * exists). `files`: the folder's `*.webp` as import.meta.glob gives them (path -> URL). `index`: the glob of the folder's
 * index.json ({key: file}) when its files are named by an index, as the sinner cards and theme pack covers are; without one,
 * a key's file is `<key>.webp`. */
export function webpFolder(files: Record<string, string>, index?: Record<string, Record<string, string>>) {
  const byName = new Map(Object.entries(files).map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1), url]));
  const names = index && (Object.values(index)[0] ?? {});
  return (key: string | number): string | undefined => {
    const name = names ? names[key] : `${key}.webp`;
    return name === undefined ? undefined : byName.get(name);
  };
}
