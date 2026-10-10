import { test, expect } from "../../../../frontend/tooling/web-test";
import {
  ownedLoopbackPort,
  ownedEndpoints,
  assertOwnedListener,
  assertOwnedBuild,
  linuxListenerInode,
} from "../owned-listeners";
test("自有3470/3471由已校验Origin解析，原3460/3461亦可用，不默认旧端口", () => {
  expect(
    ownedEndpoints(
      {
        web_origin: "http://127.0.0.1:3470",
        api_origin: "http://127.0.0.1:3471",
        web_pid: 1234,
        api_pid: 1235,
      },
      "http://127.0.0.1:3470",
    ),
  ).toEqual([
    { port: 3470, pid: 1234 },
    { port: 3471, pid: 1235 },
  ]);
  expect(ownedLoopbackPort("http://127.0.0.1:3460")).toBe(3460);
  expect(ownedLoopbackPort("http://127.0.0.1:3461")).toBe(3461);
  expect(ownedLoopbackPort("http://127.0.0.1:65535")).toBe(65535);
});
test("Linux实际socket行只接受唯一当前UID的IPv4 loopback；外部/重复/异UID/缺socket拒绝", () => {
  const row =
    " 0: 0100007F:0DA2 00000000:0000 0A 00000000:00000000 00:00000000 00000000 1001 0 20770218 1";
  const table = "header\n" + row + "\n";
  expect(linuxListenerInode(table, "header\n", 3490, 1001)).toBe("20770218");
  for (const [tcp, tcp6, uid] of [
    ["header\n", "header\n", 1001],
    [table, "header\n", 1002],
    [table.replace("0100007F", "00000000"), "header\n", 1001],
    [table + row + "\n", "header\n", 1001],
    [
      table,
      "header\n" +
        row.replace("0100007F", "00000000000000000000000000000000") +
        "\n",
      1001,
    ],
    [table.replace("20770218", "0"), "header\n", 1001],
  ] as const)
    expect(() => linuxListenerInode(tcp, tcp6, 3490, uid)).toThrow();
});
test("拒绝异主机/非本地HTTP/userinfo/path/query/hash/无效或隐式端口，不echo输入", () => {
  for (const origin of [
    null,
    3470,
    "https://127.0.0.1:3470",
    "http://localhost:3470",
    "http://[::1]:3470",
    "http://127.0.0.2:3470",
    "http://127.0.0.1.attacker.invalid:3470",
    "http://u:p@127.0.0.1:3470",
    "http://127.0.0.1:3470/",
    "http://127.0.0.1:3470/path",
    "http://127.0.0.1:3470?q=1",
    "http://127.0.0.1:3470#part",
    "http://127.0.0.1",
    "http://127.0.0.1:0",
    "http://127.0.0.1:65536",
    "http://127.0.0.1:-1",
    "http://127.0.0.1:1e3",
    "http://127.0.0.1:03470",
    " http://127.0.0.1:3470",
  ])
    expect(() => ownedLoopbackPort(origin)).toThrow(/Invalid owned/);
});
test("窗口Origin与当前入口一致、PID正整数，listener只能精确自有PID", () => {
  const window = {
    web_origin: "http://127.0.0.1:3470",
    api_origin: "http://127.0.0.1:3471",
    web_pid: 1234,
    api_pid: 1235,
  };
  expect(() => ownedEndpoints(window, "http://127.0.0.1:3460")).toThrow(
    "origin mismatch",
  );
  for (const pid of [null, 0, -1, 1.1, "1234", Number.MAX_SAFE_INTEGER + 1])
    expect(() =>
      ownedEndpoints({ ...window, api_pid: pid }, window.web_origin),
    ).toThrow("process identity");
  assertOwnedListener("1234\n", 1234);
  assertOwnedListener("1234\n1234\n", 1234);
  for (const result of ["", "1235\n", "1234\n1235\n", "invalid\n", "01234\n"])
    expect(() => assertOwnedListener(result, 1234)).toThrow(
      "listener mismatch",
    );
});
test("保留当前checkout build证明，缺失/异build拒绝", () => {
  assertOwnedBuild("owned-test-build", "owned-test-build\n");
  for (const build of [null, "", "another-build"])
    expect(() => assertOwnedBuild(build, "owned-test-build")).toThrow(
      "source build mismatch",
    );
});
