// The UI text keeps the ASD-STE100 (Issue 9) writing rules a program can check (#664). STE is written for English; the Chinese
// text keeps the same limits in characters: a Chinese sentence of 40 characters stands for STE's 25 words (about 1.6 characters
// a word). A "\n" in a text starts a new paragraph (ui.tsx `lines`).
import { describe, expect, test } from "vitest";
import { TEXT } from "./i18n";

type Lang = keyof typeof TEXT;
const LIMIT: Record<Lang, number> = { en_us: 25, zh_tw: 40 };

/** R8.5 and R8.6: a placeholder, a quoted label and the text in parentheses each count as one word. */
const oneWord = (text: string) =>
  text.replace(/\{\w+\}/g, " X ").replace(/「[^」]*」|"[^"]*"|（[^）]*）|\([^)]*\)/g, " X ");

/** English: each word. Chinese: each character, and each run of Latin letters or digits (a game name, a number). */
const words = (lang: Lang, sentence: string) => {
  const s = oneWord(sentence);
  const latin = s.match(/[A-Za-z0-9][A-Za-z0-9.'’+#-]*/g)?.length ?? 0;
  return lang === "en_us" ? latin : latin + (s.match(/[㐀-鿿]/g)?.length ?? 0);
};

const paragraphs = (text: string) => text.split("\n");
const sentences = (lang: Lang, paragraph: string) =>
  (lang === "en_us" ? paragraph.split(/(?<=[.?!])\s+/) : paragraph.split(/(?<=[。？！?!])/)).filter((s) => s.trim());

/** What `faults` finds in each text of both languages, as "<lang> <key>: <fault>"; empty when every text keeps the rule. */
const offenders = (faults: (lang: Lang, text: string) => string[]) =>
  (Object.keys(TEXT) as Lang[]).flatMap((lang) =>
    Object.entries(TEXT[lang]).flatMap(([key, text]) => faults(lang, text).map((fault) => `${lang} ${key}: ${fault}`)));

describe("the UI text keeps the STE rules a program can check", () => {
  test("no semicolon (R8.1)", () => {
    expect(offenders((_, text) => (/[;；]/.test(text) ? [text] : []))).toEqual([]);
  });

  test("a sentence has at most 25 words, or 40 Chinese characters (R6.3)", () => {
    expect(offenders((lang, text) => paragraphs(text).flatMap((p) => sentences(lang, p))
      .filter((s) => words(lang, s) > LIMIT[lang]).map((s) => `(${words(lang, s)}) ${s}`))).toEqual([]);
  });

  test("a paragraph has at most six sentences (R6.6)", () => {
    expect(offenders((lang, text) => paragraphs(text).filter((p) => sentences(lang, p).length > 6))).toEqual([]);
  });

  test("both languages split a text into the same paragraphs", () => {
    const bad = Object.keys(TEXT.zh_tw).filter((k) => {
      const key = k as keyof typeof TEXT.zh_tw;
      return paragraphs(TEXT.zh_tw[key]).length !== paragraphs(TEXT.en_us[key]).length;
    });
    expect(bad).toEqual([]);
  });

  test("the counts follow the rules' own examples", () => {
    // R8.5/R8.6: "(Lunacy)" and a placeholder count as one word each; a Chinese label in 「」 counts as one.
    expect(words("en_us", "It spends Lunacy (free first, then paid) on {n} charges.")).toBe(7);
    expect(words("zh_tw", "在任務清單勾選「狂氣換腦啡肽」。")).toBe(8);
    expect(words("zh_tw", "價格是 26、52、78。")).toBe(6);
  });
});
