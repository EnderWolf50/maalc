// The built GUI runs under tauri.conf.json's CSP (the dev page does not, #164): what vite inlines has to pass it.
import { expect, test } from "vitest";
import conf from "../src-tauri/tauri.conf.json";

const directive = (name: string) =>
  conf.app.security.csp.split(";").map((d) => d.trim().split(/\s+/)).find(([n]) => n === name)?.slice(1);

test("images come from the app itself and from Tauri's asset protocol, which serves the game's art out of the install's data folder (#767); no data: URL", () => {
  expect(directive("img-src")).toEqual(["'self'", "asset:", "http://asset.localhost"]);
});

test("the asset protocol is on, and its static scope names nothing: lib.rs grants the install's data folder when the app starts", () => {
  expect(conf.app.security.assetProtocol).toEqual({ enable: true, scope: [] });
});

test("scripts come only from the app itself: the settings validator is compiled at build time, so no 'unsafe-eval', in dev too: no devCsp (#220)", () => {
  expect(directive("script-src")).toEqual(["'self'"]);
  expect("devCsp" in conf.app.security).toBe(false);
});

test("nothing else is opened up: fonts, styles and the like fall back to the app itself, and connections go to Tauri's IPC only", () => {
  expect(directive("default-src")).toEqual(["'self'"]);
  expect(directive("connect-src")).toEqual(["'self'", "ipc:", "http://ipc.localhost"]);
});
