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
