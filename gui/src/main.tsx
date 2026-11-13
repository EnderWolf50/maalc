import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
// The condensed face of numerals and Latin game words (OFL), bundled: the app runs offline under a self-only CSP.
import "@fontsource/barlow-condensed/latin-600.css";
import "@fontsource/barlow-condensed/latin-700.css";
import "./index.css";

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
