// Synthetic contract/component fixtures. No API, PostgreSQL, Woo or provider proof.
import { offlineEnvelope, offlineId, offlineSession } from "../../../../frontend/lib/b04-offline-source";
import type { DTO } from "../../../../frontend/lib/p3-present";
import type { WooN01Input, WooN01Response } from "../../../../frontend/lib/p4-n01";
import mockN01 from "../phase4/n01.fixture.json";
export const shop = offlineId(101);
export const version = "synthetic-woo-config-v1";
export function wooConfig(kind = "woo", sourceVersion = version): DTO["ConfigRead"] {
  const base = offlineSession().config;
  const config: DTO["DeploymentConfig"] = kind === "mock" ? base : {
    ...base, source_mode: "woocommerce_test",
    ...(kind === "missing" ? {} : { commerce_source: {
      schema_version: "p5-commerce-source-v1" as const, source_kind: "woocommerce_test" as const,
      source_config_version: kind === "disabled" ? null : sourceVersion,
      creation_enabled: kind !== "disabled",
    } }),
  };
  return { ...offlineEnvelope, shop_id: shop, config };
}
export function wooInput(text = mockN01.cases[0].text): WooN01Input {
  return { schema_version: "p3-web-v1", source_mode: "woocommerce_test", shop_id: shop,
    source_config_version: version, text };
}
export function wooN01(input = wooInput()): WooN01Response {
  // Reuse frozen parser candidates for these exact sentences; do not implement a second parser.
  const sample = mockN01.cases.find((row) => row.text === input.text);
  if (!sample) throw new Error("No frozen synthetic candidate fixture for this sentence");
  const old = structuredClone(sample.result);
  return {
    ...offlineEnvelope,
    preflight: {
      ...old, schema_version: "p5-n01-web-v1", shop_id: input.shop_id,
      source: { source_mode: "woocommerce_test", source_config_version: input.source_config_version, evidence_mode: "not_used" },
      window: { ...old.window, source: "commerce_configuration" },
      scope: { kind: "all_shop_products", shop_id: input.shop_id, source: "selected_shop" },
      draft: old.draft ? { source_mode: "woocommerce_test", source_config_version: input.source_config_version,
        L: old.draft.L, R: old.draft.R, S: old.draft.S } : null,
    } as WooN01Response["preflight"],
  };
}
export const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), {
  status, headers: { "Content-Type": "application/json" },
});
export function operatorSession() {
  const read = offlineSession();
  return { ...read, principal: { ...read.principal,
    role_shop_grants: [{ role: "operator" as const, shop_id: shop }],
    capabilities: { ...read.principal.capabilities, can_create_task: true },
  } };
}
