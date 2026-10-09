"""核对设计合同与真实 MCP/重启回读的引用完整性，不运行业务代码。"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
UX = ROOT / "docs/ux"


def read(path):
    return json.loads(path.read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    screens = read(UX / "screens.yaml")
    interactions = read(UX / "interactions.yaml")
    tokens = read(UX / "design-tokens.json")
    mapping = read(UX / "evidence/design-map.json")
    all_screens = screens["poc_screens"] + screens["planned_screens"]
    ids = [s["id"] for s in all_screens]
    require(len(ids) == len(set(ids)), "Screen ID 重复")
    events = interactions["poc_interactions"] + interactions["planned_interactions"]
    for key in ["id", "control_id"]:
        values = [e[key] for e in events]
        require(len(values) == len(set(values)), "Event/control ID 重复")
    for e in events:
        require(e["screen_id"] in ids and e["target_screen"] in ids, "事件页面引用不存在")
        require(set(e["roles"]) <= screens["roles"].keys(), "未知角色")
    actual_controls = {c["id"]: c for c in mapping["controls"]}
    actual_screens = {s["name"].split(" / ")[0]: s["id"] for s in mapping["screens"]}
    for s in screens["poc_screens"]:
        require(s["penpot"]["shape_id"] == actual_screens[s["id"]], "画板映射不一致")
        require(s["penpot"]["file_id"] == mapping["file"]["id"], "文件映射不一致")
        require(s["penpot"]["revision"] == mapping["revision"], "视觉版本不一致")
    for e in interactions["poc_interactions"]:
        c = actual_controls[e["penpot_shape_id"]]
        require(c["stableId"].split(" / ")[0] == e["control_id"], "控制件稳定 ID 不一致")
        action = c["interactions"][0]
        require(action["type"] == e["action"] and action["trigger"] == e["event"], "原型动作不一致")
        require(action["destination"] == actual_screens[e["target_screen"]], "原型目标不一致")
    for s in screens["planned_screens"]:
        require(s["status"] == "planned_unmapped" and s["penpot"] is None, "计划不得冒充画布")
    require(tokens["penpot_revision"] == mapping["revision"], "POC token 版本不一致")
    require(mapping["validation"] == [], "Penpot 原生文件校验有错误")
    restored = read(UX / "evidence/after-restart-read.json")
    payload = json.loads(restored["result"]["content"][0]["text"])["result"]
    require(payload["fileId"] == mapping["file"]["id"], "重启后文件改变")
    require(payload["purpose"] == "tool-verification-only", "版本恢复未回到原标记")
    require(payload["revision"] == mapping["revision"], "重启后版本改变")
    require({c["id"] for c in payload["controls"]} == set(actual_controls), "重启后控制件丢失")
    require(payload["validation"] == [], "重启后原生校验失败")
    require(
        not read(UX / "evidence/runtime-summary.json")[
            "credentials_present_in_current_container_logs"
        ],
        "设计容器日志仍有凭据",
    )
    ui = read(UX / "evidence/prototype-ui-events.json")
    after = read(UX / "evidence/prototype-after-restart.json")
    require(len(ui) == 10 and len(after) == 4, "实际原型点击记录不完整")
    require(not screens["roles"]["admin"]["approve"], "admin 不得自动有审批权")
    print(
        f"合同/画布引用一致：{len(screens['poc_screens'])} POC 屏幕、"
        "4 控制件、14 点击记录；M1 仍为草案"
    )


if __name__ == "__main__":
    main()
