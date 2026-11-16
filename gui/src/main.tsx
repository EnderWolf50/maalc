import React from "react";
import ReactDOM from "react-dom/client";
import { StartError } from "./StartError";
// The condensed face of numerals and Latin game words (OFL), bundled: the app runs offline under a self-only CSP.
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/barlow-condensed/latin-700.css";
import "@fontsource/barlow-condensed/latin-800.css"; // the deployment order's numbers (index.css .sinner .num)
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);

// The game data is read when ./App's modules load (gameData.ts), so App comes in by import(): a folder or file that cannot
// be read rejects it, and the window says why instead of staying blank.
import("./App").then(async ({ default: App }) => {
  (await import("./gameData")).applyArt();
  root.render(<React.StrictMode><App /></React.StrictMode>);
}, (error) => root.render(<StartError error={error} />));
