import { test, expect } from "@playwright/test";
import { validRoleMap, validShopScopes } from "../m3-live/owned-m3-input";
import type { Seed } from "../m3-live/owned-m3-input";
const daily = "00000000-0000-0000-0000-000000000001", commerce = "00000000-0000-0000-0000-000000000002";
const roles = (a: ("operator" | "approver")[], b: ("operator" | "approver")[]) => ({ [daily]: a, [commerce]: b });
const base = { daily_shop_id: daily, inquiry_shop_id: commerce, copy: { shop_id: commerce }, owner: { shop_roles: roles(["operator"],["operator"]) }, reviewer: { shop_roles: roles([],["approver"]) }, unassigned: { shop_roles: roles([],["approver"]) }, outside: { home_path: "/tasks", shop_roles: roles(["operator"],[]) } } as unknown as Seed;
test("synthetic daily and inquiry/copy source scopes remain distinct", () => {
 expect(validShopScopes(base)).toBe(true);
 expect(validShopScopes({ ...base, inquiry_shop_id: daily })).toBe(false);
 expect(validShopScopes({ ...base, copy: { ...base.copy, shop_id: daily } })).toBe(false);
 expect(validShopScopes({ ...base, owner: { ...base.owner, shop_roles: roles(["operator"],[]) } })).toBe(false);
 expect(validShopScopes({ ...base, reviewer: { ...base.reviewer, shop_roles: roles(["approver"],[]) } })).toBe(false);
 expect(validShopScopes({ ...base, outside: { ...base.outside, shop_roles: roles(["operator"],["operator"]) } })).toBe(false);
 expect(validShopScopes({ ...base, outside: { ...base.outside, shop_roles: roles([],[]) } })).toBe(false);
 expect(validShopScopes({ ...base, outside: { ...base.outside, home_path: "/access" } })).toBe(false);
 expect(validRoleMap({ [daily]: ["operator"] }, [daily, commerce])).toBe(false);
 expect(validRoleMap(roles(["operator", "operator"], []), [daily, commerce])).toBe(false);
});
