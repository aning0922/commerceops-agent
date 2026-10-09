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


def check_b1b(screens, interactions):
    """核对本批实际回读、完整披露和失败后的复验，不运行业务。"""
    sample = read(UX / "evidence/c2-b1b/design-map.json")
    saved = read(UX / "evidence/c2-b1b/after-reload-read.json")
    clicks = read(UX / "evidence/c2-b1b/prototype-ui-events.json")["events"]
    require(sample["revision"] == saved["revision"], "B1b刷新后版本改变")
    require(sample["file"]["id"] == saved["fileId"], "B1b文件改变")
    require(sample["validation"] == saved["validation"] == [], "B1b原生校验失败")
    require(not saved["overflow"] and not saved["outside"], "B1b布局溢出")
    require(sample["counts"]["imageFills"] == 0, "B1b不是原生可编辑界面")
    boards = {s["shapeId"]: s for s in sample["screens"]}
    require(set(boards) == {s["shapeId"] for s in saved["screens"]}, "B1b界面UUID改变")
    for screen in screens["planned_screens"]:
        if screen["penpot"]:
            actual = boards[screen["penpot"]["shape_id"]]
            require(actual["stableId"] == screen["id"], "B1b页面ID不一致")
            require(screen["penpot"]["revision"] == sample["revision"], "B1b页面版本不一致")
    controls = {c["shapeId"]: c for c in sample["controls"]}
    reread = {c["shapeId"]: c for c in saved["controls"]}
    require(set(controls) == set(reread), "B1b控件UUID改变")
    for shape_id, control in controls.items():
        require(control["stableId"] == reread[shape_id]["stableId"], "B1b控件ID改变")
        require(control["eventId"] == reread[shape_id]["eventId"], "B1b事件ID改变")
        require(control["interactions"], "B1b控件没有原型目标")
        for expected, actual in zip(
            control["interactions"], reread[shape_id]["interactions"], strict=True
        ):
            require(
                all(expected.get(k) == actual.get(k) for k in ["type", "trigger", "destination"]),
                "B1b刷新后动作改变",
            )
    for event in interactions["planned_interactions"]:
        for instance in event.get("penpot_instances", []):
            actual = controls[instance["shape_id"]]
            require(actual["stableId"] == event["control_id"], "B1b实例控件ID错误")
            require(actual["eventId"] == event["id"], "B1b实例事件ID错误")
    require(not any(c["stableId"] == "M1-B09" for c in controls.values()), "禁止手动恢复入口")
    for name, count, total, unknown in [
        ("main", 3, 195, 1),
        ("one", 1, 100, 0),
        ("twenty", 20, 2276, 4),
    ]:
        items = sample["fixtures"][name]["items"]
        require(len(items) == count, "冻结范围数量错误")
        require(sum(i["qty"] for i in items) == total, "冻结范围件数错误")
        require(sum(i["inbound"] is None for i in items) == unknown, "未知假设集合错误")
        for item in items:
            require(
                item["qty"] == max(0, item["target"] - item["stock"] - (item["inbound"] or 0)),
                "Mock SKU确定性公式错误",
            )
    require(
        any(v["label"] == sample["named_version"] for v in saved["versions"]),
        "B1b命名版本丢失",
    )
    require(len(clicks) >= 73, "B1b实际点击记录缺失")
    require(any(c["action"] == "background_click" and c["passed"] for c in clicks), "缺留白点击")
    require(any(c["controlId"] == "M1-B03" and c["passed"] for c in clicks), "缺未知假设批准实点")
    require(any(c["controlId"] == "M1-B04" and c["passed"] for c in clicks), "缺未知假设拒绝实点")
    require(any(c["controlId"] == "M1-B07" and c["passed"] for c in clicks), "缺完成分支")
    require(any(c["controlId"] == "M1-B08" and c["passed"] for c in clicks), "缺关闭分支")
    require(not screens["followup_authorization"]["C2-B2"], "不得启动B2")
    require(not screens["followup_authorization"]["C2-B3"], "不得启动B3")
    print("M1 B1b：原生UUID/命名版本/冻结清单与实际Viewer记录一致；业务未实现")


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
        if s["penpot"] is None:
            require(s["status"] == "planned_unmapped", "未映射计划状态不一致")
        else:
            require(s["status"] == "visual_sample_mapped", "样板不得冒充完整业务页面")
            require(s["implementation_status"] == "not_implemented", "原型不是业务实现")
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
    if screens.get("m1_visual_map"):
        sample = read(UX / "evidence/c2-b1a/design-map.json")
        saved = read(UX / "evidence/c2-b1a/after-reload-read.json")
        clicks = read(UX / "evidence/c2-b1a/prototype-ui-events.json")["events"]
        require(sample["file"]["id"] != mapping["file"]["id"], "正式文件不能覆盖POC")
        require(sample["validation"] == saved["validation"] == [], "正式原生校验失败")
        require(saved["revision"] == sample["revision"], "刷新后视觉版本改变")
        samples = {s["stableId"]: s for s in sample["screens"]}
        for s in screens["planned_screens"]:
            if s["penpot"] and s["id"] in samples:
                require(s["penpot"]["shape_id"] == samples[s["id"]]["shapeId"], "M1 UUID不一致")
                require(s["penpot"]["file_id"] == saved["fileId"], "M1文件不一致")
        controls = {c["shapeId"]: c for c in sample["controls"]}
        saved_controls = {c["shapeId"]: c for c in saved["controls"]}
        require(set(controls) == set(saved_controls), "刷新后控件集合改变")
        for shape_id, actual in controls.items():
            reread = saved_controls[shape_id]
            require(actual["stableId"] == reread["stableId"], "刷新后稳定ID改变")
            expected_actions = [
                {k: a[k] for k in ["trigger", "type", "destination"]}
                for a in actual["interactions"]
            ]
            require(expected_actions == reread["interactions"], "刷新后原型动作改变")
        require(
            any(v["label"] == sample["named_version"] for v in saved["versions"]),
            "命名版本未保存",
        )
        for event in interactions["planned_interactions"]:
            for instance in event.get("penpot_instances", []):
                if instance["revision"] != sample["revision"]:
                    continue
                actual = controls[instance["shape_id"]]
                require(actual["stableIdReadback"] == event["control_id"], "M1控件ID不一致")
                require(actual["eventIdReadback"] == event["id"], "M1事件ID不一致")
        require(len(clicks) == 28 and all(c["passed"] for c in clicks), "B1a实点记录未通过")
        require(sample["counts"]["imageFills"] == 0, "正式页面不能用整张图片代替")
        require(
            all(not s["textOverflow"] and not s["outOfBoard"] for s in samples.values()), "样板溢出"
        )
        if screens.get("m1_visual_revision") == "m1-ui/0.2.0-b1b":
            check_b1b(screens, interactions)
        else:
            require(screens["authorization_scope"] == "C2-B1a_only", "设计授权范围错误")
            require(not any(screens["followup_authorization"].values()), "后续批次未获授权")
        print("M1 B1a：5个原生样板/辅助层、14控件实例、28实点；业务未实现")
    print(
        f"合同/画布引用一致：{len(screens['poc_screens'])} POC 屏幕、"
        "4 控制件、14 点击记录；M1 业务未实现"
    )


if __name__ == "__main__":
    main()
