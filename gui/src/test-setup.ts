// Vitest setup: the jest-dom matchers (toBeDisabled, toHaveAttribute, ...) and a clean DOM between tests.
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(cleanup);
