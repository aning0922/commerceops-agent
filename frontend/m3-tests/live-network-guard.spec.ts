import { test, expect } from "@playwright/test";
import { allowedOwnedRequest } from "../m3-live/network-guard";
const web = "http://127.0.0.1:14001", api = "http://127.0.0.1:14002";
const task = "00000000-0000-4000-8000-000000000001";
const check = (url: string, method = "GET") => allowedOwnedRequest(url, method, web, api, task);
test("owned live guard permits only the registered read paths and login", () => {
  expect(check(`${api}/api/v1/auth/login`, "POST")).toBe(true);
  expect(check(`${api}/api/v1/auth/session`)).toBe(true);
  expect(check(`${api}/api/v1/daily-reports/${task}`)).toBe(true);
  expect(check(`${web}/daily-reports/${task}`)).toBe(true);
  expect(check(`${web}/_next/static/chunk.js`)).toBe(true);
  expect(check(`${api}/api/v1/tasks`, "POST")).toBe(false);
  expect(check(`${api}/api/v1/auth/login?redirect=elsewhere`, "POST")).toBe(false);
  expect(check(`${api}/api/v1/daily-reports/other`)).toBe(false);
});
test("wrong API origin cannot receive login or any API request", () => {
  expect(check("http://127.0.0.1:14003/api/v1/auth/login", "POST")).toBe(false);
  expect(check(`${web}/api/v1/auth/login`, "POST")).toBe(false);
  expect(check("https://example.invalid/api/v1/auth/session")).toBe(false);
  expect(check(`${web}/api/v1/auth/session`)).toBe(false);
  expect(check("http://127.0.0.1:14003/api/v1/auth/session")).toBe(false);
  expect(check(`${api}/api/v1/config`, "DELETE")).toBe(false);
  expect(check("ws://127.0.0.1:14002/api/v1/socket")).toBe(false);
});

test("owned login waits for exact home URL, live shell and loaded task list in order", async () => {
  const { isOwnedHome, waitForOwnedHome } = await import("../m3-live/owned-home-ready");
  const origin = "http://127.0.0.1:3410", events: string[] = [];
  expect(isOwnedHome(new URL(origin + "/tasks"), origin, "/tasks")).toBe(true);
  for (const url of [origin + "/login", origin + "/tasks?probe=one", origin + "/tasks#fragment", "http://127.0.0.1:3411/tasks"]) expect(isOwnedHome(new URL(url), origin, "/tasks")).toBe(false);
  let release!: () => void;
  const navigation = new Promise<void>(resolve => { release = resolve; });
  const page = {
    waitForURL: async (match: (url: URL) => boolean, options: { waitUntil: string }) => { events.push("navigation"); expect(options.waitUntil).toBe("commit"); expect(match(new URL(origin + "/tasks"))).toBe(true); await navigation; },
    locator: (selector: string) => selector === "main#main" ? { getByRole: (_: string, options: { name: string }) => ({ waitFor: async () => { events.push(options.name); } }) } : { waitFor: async () => { events.push("shell"); } },
    url: () => origin + "/tasks",
  };
  let finished = false;
  const pending = waitForOwnedHome(page as never, origin, "/tasks").then(() => { finished = true; });
  await Promise.resolve(); expect(events).toEqual(["navigation"]); expect(finished).toBe(false);
  release(); await pending; expect(events).toEqual(["navigation", "shell", "任务中心", "任务列表"]);
});

test("owned home failure is safely classified without URL or response details", async () => {
  const { waitForOwnedHome } = await import("../m3-live/owned-home-ready");
  const page = { waitForURL: async () => { throw new Error("http://private/?probe=one"); } };
  await expect(waitForOwnedHome(page as never, "http://127.0.0.1:3410", "/tasks")).rejects.toThrow(/^Owned login home navigation not ready$/);
});

test("access-only home requires its own heading and refuses a late navigation", async () => {
  const { waitForOwnedHome } = await import("../m3-live/owned-home-ready");
  const origin = "http://127.0.0.1:3410", seen: string[] = [];
  const page = { waitForURL: async () => {}, locator: (selector: string) => selector === "main#main" ? { getByRole: (_: string, options: { name: string }) => ({ waitFor: async () => { seen.push(options.name); } }) } : { waitFor: async () => {} }, url: () => origin + "/access?unexpected=1" };
  await expect(waitForOwnedHome(page as never, origin, "/access")).rejects.toThrow(/^Owned login home navigation not ready$/);
  expect(seen).toEqual(["访问限制与会话过期", "无法访问此页面"]);
});
