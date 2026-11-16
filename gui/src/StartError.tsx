// What the window shows when it cannot start, most likely because the game data cannot be read (main.tsx). It imports nothing
// of the app, which is the part that failed to load, so both languages are written here. The window has no title bar of its own
// (tauri.conf.json), so the page brings its own way to close it.
import { closeWindow } from "./api";

export function StartError({ error }: { error: unknown }) {
  const reason = error instanceof Error ? error.message : String(error);
  return (
    <main className="start-error" role="alert">
      <h1>無法讀取遊戲資料 / Cannot read the game data</h1>
      <p>設定視窗要讀安裝資料夾裡的 resource/base/data。請確認這個程式和 resource 資料夾放在一起，或重新解壓縮 maalc。</p>
      <p>The settings window reads resource/base/data beside this program. Check that the resource folder is there, or unpack maalc again.</p>
      <pre>{reason}</pre>
      <button type="button" onClick={() => { closeWindow(); }}>關閉 / Close</button>
    </main>
  );
}
