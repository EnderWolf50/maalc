// A drag held near the top or bottom edge of the box it scrolls in scrolls that box (dragScroll.ts, #916). jsdom lays nothing
// out: each test gives the scrolling box its place and sizes (`layOut`), and the drag events say where the pointer is.
import { createEvent, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import App from "./App";
import { EDGE_SPEED, EDGE_ZONE, edgeSpeed, useDragScroll } from "./dragScroll";
import { newSettings, type Settings } from "./model";
import { PACK_EN, pickInList } from "./testing";
import userEvent from "@testing-library/user-event";

const file = vi.hoisted(() => ({ text: "" }));
vi.mock("./api", async (original) => ({
  ...(await original<typeof import("./api")>()),
  loadSettings: () => Promise.resolve(file.text),
  saveSettings: () => Promise.resolve(),
  rootDir: () => Promise.resolve("root"),
}));

const dt = () => ({ setData() {}, effectAllowed: "", dropEffect: "" });

/** A drag event at `el` with the pointer's height and the element it went into, as the browser's carry them: jsdom has no
 * DragEvent, so fireEvent's plain Event would drop clientY and relatedTarget. */
function dragAt(type: "dragOver" | "dragLeave", el: Element, init: { clientY?: number; relatedTarget?: EventTarget | null }) {
  const e = createEvent[type](el, { dataTransfer: dt() });
  for (const [key, value] of Object.entries(init)) Object.defineProperty(e, key, { value });
  fireEvent(el, e);
}

/** Give `box` the place of a scrolling page in the window (CSS px): its visible part from `top` to `top + height`, its
 * content `content` tall. */
function layOut(box: HTMLElement, top: number, height: number, content: number) {
  box.getBoundingClientRect = () => DOMRect.fromRect({ x: 0, y: top, width: 800, height });
  Object.defineProperty(box, "clientHeight", { configurable: true, value: height });
  Object.defineProperty(box, "scrollHeight", { configurable: true, value: content });
}

// The page that scrolls: from 100 to 700 in the window (jsdom's is 768 tall), 3000 px of content.
const TOP = 100, BOTTOM = 700;

describe("the speed at a height", () => {
  test("nothing away from the edges; inside the zone it grows toward the edge, the edge's speed at it and past it", () => {
    expect(edgeSpeed(400, TOP, BOTTOM)).toBe(0);
    expect(edgeSpeed(BOTTOM - EDGE_ZONE, TOP, BOTTOM)).toBe(0);
    const half = edgeSpeed(BOTTOM - EDGE_ZONE / 2, TOP, BOTTOM), near = edgeSpeed(BOTTOM - 5, TOP, BOTTOM);
    expect(half).toBeGreaterThan(0);
    expect(near).toBeGreaterThan(half);
    expect(edgeSpeed(BOTTOM, TOP, BOTTOM)).toBe(EDGE_SPEED);
    expect(edgeSpeed(BOTTOM + 50, TOP, BOTTOM)).toBe(EDGE_SPEED); // below the box, still in the window
    expect(edgeSpeed(TOP + EDGE_ZONE / 2, TOP, BOTTOM)).toBe(-half); // the top edge scrolls up as fast
    expect(edgeSpeed(TOP - 30, TOP, BOTTOM)).toBe(-EDGE_SPEED); // over the tab bar above the page
  });

  test("a short box keeps its middle half still: the zone is a quarter of its height at most", () => {
    expect(edgeSpeed(150, 100, 300)).toBe(0); // 200 px tall: 50 px zones
    expect(edgeSpeed(140, 100, 300)).toBeLessThan(0);
  });
});

describe("a drag held near an edge", () => {
  function Page({ refuse = false }: { refuse?: boolean }) {
    useDragScroll();
    return (
      <main data-testid="page" style={{ overflowY: "auto" }}>
        <div data-testid="bar">picked: 2</div>
        <span data-testid="item" draggable onDragStart={(e) => { if (refuse) e.preventDefault(); }}>a pack</span>
        <div data-testid="lane">a lane</div>
      </main>
    );
  }
  const page = () => screen.getByTestId("page");
  /** Pick up the item and hold it at height `y` over `over` (the lane unless named), as the browser's dragover says. */
  const hold = (y: number, over = "lane") => dragAt("dragOver", screen.getByTestId(over), { clientY: y });
  const start = () => fireEvent.dragStart(screen.getByTestId("item"), { dataTransfer: dt() });
  const wait = (ms: number) => vi.advanceTimersByTime(ms);

  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  function setUp(props: { refuse?: boolean } = {}, scrollTop = 0) {
    render(<Page {...props} />);
    layOut(page(), TOP, BOTTOM - TOP, 3000);
    page().scrollTop = scrollTop;
  }

  test("near the bottom edge the page scrolls down, faster the nearer the edge", () => {
    setUp();
    start();
    hold(BOTTOM - EDGE_ZONE / 2);
    wait(500);
    const halfway = page().scrollTop;
    expect(halfway).toBeGreaterThan(0);
    hold(BOTTOM - 2);
    wait(500);
    expect(page().scrollTop - halfway).toBeGreaterThan(halfway);
  });

  test("near the top edge it scrolls up, also with the pointer over a bar held at the page's top", () => {
    setUp({}, 2000);
    start();
    hold(TOP + 10, "bar");
    wait(500);
    expect(page().scrollTop).toBeLessThan(2000);
  });

  test("away from the edges the page stays, and it stops when the pointer leaves the edge", () => {
    setUp();
    start();
    hold(400);
    wait(500);
    expect(page().scrollTop).toBe(0);
    hold(BOTTOM - 5);
    wait(300);
    const at = page().scrollTop;
    expect(at).toBeGreaterThan(0);
    hold(400);
    wait(500);
    expect(page().scrollTop).toBe(at);
  });

  test.each([
    ["dropped", () => fireEvent.drop(screen.getByTestId("lane"), { dataTransfer: dt() })],
    // Esc cancels a drag in the browser, which ends it with dragend: no keydown reaches the page during a drag
    ["cancelled with Esc", () => fireEvent.dragEnd(screen.getByTestId("item"), { dataTransfer: dt() })],
  ])("a drag %s stops the scroll", (_, end) => {
    setUp();
    start();
    hold(BOTTOM - 5);
    wait(300);
    end();
    const at = page().scrollTop;
    expect(at).toBeGreaterThan(0);
    wait(500);
    expect(page().scrollTop).toBe(at);
  });

  test("the pointer leaving the window stops it until it comes back", () => {
    setUp();
    start();
    hold(BOTTOM - 5);
    wait(300);
    dragAt("dragLeave", screen.getByTestId("lane"), { relatedTarget: null }); // out of the window: into no element
    const at = page().scrollTop;
    wait(500);
    expect(page().scrollTop).toBe(at);
    hold(BOTTOM - 5);
    wait(300);
    expect(page().scrollTop).toBeGreaterThan(at);
  });

  test("a drag the list refused at its start scrolls nothing", () => {
    setUp({ refuse: true });
    start();
    hold(BOTTOM - 5);
    wait(500);
    expect(page().scrollTop).toBe(0);
  });
});

describe("in the window", () => {
  const settings = (): Settings => ({
    ...newSettings(), language: "en_us",
    theme_pack_plans: [{ id: "p1", name: "Mine", weights: { "The Outcast": 3, "Automated Factory": -5 }, threshold: 0, unlisted: 0,
      event_packs: "weight" }],
  });
  beforeEach(() => { file.text = JSON.stringify(settings()); });

  test("a theme pack held near the bottom of the page scrolls it toward the lowest lane, and a drop stops it", async () => {
    const user = userEvent.setup();
    const { container } = render(<App start="themepacks" />);
    await screen.findByText("Mine");
    await pickInList(user, "Mine");
    const main = container.querySelector("main")!;
    main.style.overflowY = "auto"; // index.css: `main { overflow: auto }`, which jsdom does not load
    layOut(main, TOP, BOTTOM - TOP, 3000);
    const pack = screen.getByText("The Outcast", { selector: PACK_EN }).closest<HTMLElement>("[data-pk]")!;
    fireEvent.dragStart(pack, { dataTransfer: dt() });
    dragAt("dragOver", main.querySelector(".lane")!, { clientY: BOTTOM - 5 });
    await waitFor(() => expect(main.scrollTop).toBeGreaterThan(0));
    fireEvent.drop(main.querySelector(".lane")!, { dataTransfer: dt() });
    const at = main.scrollTop;
    await new Promise((r) => setTimeout(r, 200));
    expect(main.scrollTop).toBe(at);
  });
});
