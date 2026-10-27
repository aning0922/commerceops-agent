import Ajv2020 from "ajv/dist/2020";
import addFormats from "ajv-formats";
import schema from "./p5-read-schema.generated.json";
import type { DTO } from "./p3-present";

export type ParameterName = "L" | "R" | "S";
export type N01Input = {
  schema_version: "p3-web-v1";
  shop_id: string;
  fixture_case: string;
  text: string;
};
export type N01Response = {
  schema_version: "p3-web-v1";
  identity_mode: "session";
  server_time: string;
  trace_id: string;
  preflight: {
    schema_version: "p4-n01-web-v1";
    status: "ready" | "clarify" | "unsupported";
    reason: "EXPLICIT_PARAMETERS" | "MISSING_PARAMETERS" | "INVALID_PARAMETERS" | "UNSUPPORTED_TEXT";
    shop_id: string;
    source: {
      source_mode: "mock";
      dataset_version: "inventory-v1";
      fixture_case: string;
      evidence_mode: "not_used";
    };
    window: {
      kind: "last_seven_complete_days";
      start: string;
      end: string;
      timezone: string;
      as_of: string;
      source: "mock_fixture";
    };
    scope: { kind: "all_fixture_products"; shop_id: string; source: "selected_shop" };
    candidates: {
      name: ParameterName;
      value: number;
      source: "explicit_text" | "demo_assumption";
      start: number | null;
      end: number | null;
    }[];
    missing: ParameterName[];
    draft: Extract<DTO["CreateNewCycle"]["parameters"], { source_mode: "mock" }> | null;
    requires_confirmation: true;
    execution_available: false;
  };
};
export type WooN01Input = {
  schema_version: "p3-web-v1";
  source_mode: "woocommerce_test";
  shop_id: string;
  source_config_version: string;
  text: string;
};
export type WooN01Response = Omit<N01Response, "preflight"> & {
  preflight: Omit<N01Response["preflight"], "schema_version" | "source" | "window" | "scope" | "draft"> & {
    schema_version: "p5-n01-web-v1";
    source: { source_mode: "woocommerce_test"; source_config_version: string; evidence_mode: "not_used" };
    window: Omit<N01Response["preflight"]["window"], "source"> & { source: "commerce_configuration" };
    scope: { kind: "all_shop_products"; shop_id: string; source: "selected_shop" };
    draft: DTO["P5WooCreateParameters"] | null;
  };
};
export type AnyN01Input = N01Input | WooN01Input;
export type AnyN01Response = N01Response | WooN01Response;
const ajv = new Ajv2020({ strict: false, coerceTypes: false, useDefaults: false, removeAdditional: false });
addFormats(ajv);
const operation = schema.operations.find((row) => row.method === "POST" && row.path === "/api/v1/tasks/preflight")!;
const validateInput = ajv.compile({ ...operation.input, components: schema.components });
const validators = new Map(Object.entries(operation.responses).map(([status, response]) => [
  Number(status), ajv.compile({ ...response, components: schema.components }),
]));
const names: readonly ParameterName[] = ["L", "R", "S"];
const demo = { L: 3, R: 7, S: 2 };
const utc = (value: string) => /(?:Z|[+]00:00)$/.test(value) && Number.isFinite(Date.parse(value));
export const validN01Input = (value: AnyN01Input): boolean =>
  validateInput(value) === true && [...value.text].length <= 2000;

export function validN01Response(status: number, value: unknown): boolean {
  if (validators.get(status)?.(value) !== true) return false;
  if (status !== 200) return true;
  const read = value as AnyN01Response, p = read.preflight;
  if (p.schema_version === "p4-n01-web-v1") {
    if (p.source.source_mode !== "mock" || p.source.dataset_version !== "inventory-v1" ||
        p.window.source !== "mock_fixture" || p.scope.kind !== "all_fixture_products") return false;
  } else if (p.schema_version === "p5-n01-web-v1") {
    if (p.source.source_mode !== "woocommerce_test" || !p.source.source_config_version.trim() ||
        p.window.source !== "commerce_configuration" || p.scope.kind !== "all_shop_products") return false;
  } else return false;
  if (p.requires_confirmation !== true || p.execution_available !== false ||
      p.source.evidence_mode !== "not_used" || p.window.kind !== "last_seven_complete_days" ||
      p.scope.source !== "selected_shop" || p.scope.shop_id !== p.shop_id || !p.window.timezone ||
      ![read.server_time, p.window.start, p.window.end, p.window.as_of].every(utc) ||
      !(Date.parse(p.window.start) < Date.parse(p.window.end) && Date.parse(p.window.end) <= Date.parse(p.window.as_of)) ||
      new Set(p.candidates.map((candidate) => candidate.name)).size !== 3 ||
      new Set(p.missing).size !== p.missing.length) return false;
  for (const c of p.candidates) {
    if (!Number.isSafeInteger(c.value)) return false;
    if (c.source === "explicit_text") {
      if (!Number.isSafeInteger(c.start) || !Number.isSafeInteger(c.end) ||
          c.start === null || c.end === null || c.end <= c.start || p.missing.includes(c.name)) return false;
    } else if (c.start !== null || c.end !== null || c.value !== demo[c.name] || !p.missing.includes(c.name)) return false;
  }
  if (p.status === "ready") {
    if (p.reason !== "EXPLICIT_PARAMETERS" || p.missing.length !== 0 || p.draft === null ||
        !names.every((name) => p.candidates.some((c) => c.name === name && c.source === "explicit_text" && c.value === p.draft![name]))) return false;
    if (p.schema_version === "p4-n01-web-v1")
      return p.draft.source_mode === "mock" && p.draft.dataset_version === p.source.dataset_version && p.draft.fixture_case === p.source.fixture_case;
    return p.draft.source_mode === "woocommerce_test" && p.draft.source_config_version === p.source.source_config_version;
  }
  if (p.draft !== null) return false;
  if (p.status === "unsupported") return p.reason === "UNSUPPORTED_TEXT" && p.missing.length === 3 && p.candidates.every((c) => c.source === "demo_assumption");
  return p.reason === "MISSING_PARAMETERS" ? p.missing.length > 0
    : p.reason === "INVALID_PARAMETERS" && p.missing.length === 3 && p.candidates.every((c) => c.source === "demo_assumption");
}

// Python indices count Unicode code points. Bind source/version/shop and the exact raw text.
export function n01MatchesInput(read: AnyN01Response, input: AnyN01Input): boolean {
  const p = read.preflight, points = [...input.text];
  if (p.shop_id !== input.shop_id) return false;
  if ("source_mode" in input) {
    if (p.schema_version !== "p5-n01-web-v1" || p.source.source_config_version !== input.source_config_version) return false;
  } else if (p.schema_version !== "p4-n01-web-v1" || p.source.fixture_case !== input.fixture_case) return false;
  return p.candidates.every((c) => c.source !== "explicit_text" ||
    (c.start !== null && c.end !== null && Number.isSafeInteger(c.start) && Number.isSafeInteger(c.end) &&
     c.start >= 2 && c.end > c.start && c.end <= points.length &&
     points.slice(c.start, c.end).join("") === String(c.value) &&
     !(points[c.end] >= "0" && points[c.end] <= "9") &&
     [c.name + "=", c.name + ":"].includes(points.slice(c.start - 2, c.start).join(""))));
}
export function n01CandidateText(text: string, candidate: N01Response["preflight"]["candidates"][number]): string | null {
  return candidate.source === "explicit_text" && candidate.start !== null && candidate.end !== null
    ? [...text].slice(candidate.start, candidate.end).join("") : null;
}
