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
        if screen["penpot"] and screen["penpot"]["revision"] == sample["revision"]:
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
            if instance["revision"] != sample["revision"]:
                continue
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
    require(
        not screens["followup_authorization"]["C2-B2"] or screens.get("b2_delivery"),
        "B2授权必须有独立交付记录",
    )
    require(
        not screens["followup_authorization"]["C2-B3"] or screens.get("b3_delivery"),
        "B3授权必须有独立交付记录",
    )
    print("M1 B1b：原生UUID/命名版本/冻结清单与实际Viewer记录一致；业务未实现")


def check_b2(screens, interactions):
    """核对当前UX映射、历史保持、禁用卡片与真实Viewer证据边界。"""
    sample = read(UX / "evidence/c2-b2/design-map.json")
    saved = read(UX / "evidence/c2-b2/after-reload-read.json")
    previous = read(UX / "evidence/c2-b1b/design-map.json")
    events = read(UX / "evidence/c2-b2/prototype-ui-events.json")["events"]
    summary = read(UX / "evidence/c2-b2/verification-summary.json")
    require(screens["authorization_scope"] in {"C2-B2", "C2-B3"}, "B2历史授权范围错误")
    require("C2-B2" in screens["authorized_design_batches"], "缺B2明确授权")
    require(
        not screens["followup_authorization"]["C2-B3"] or screens.get("b3_delivery"),
        "B3授权必须有独立交付记录",
    )
    require(sample["revision"] == saved["revision"] == "m1-ui/0.3.0-b2", "B2版本错误")
    require(sample["revn"] == saved["revn"], "B2持久版本不一致")
    require(sample["file"]["id"] == saved["fileId"] == previous["file"]["id"], "正式文件改变")
    require(sample["validation"] == saved["validation"] == [], "B2原生校验失败")
    require(not saved["overflow"] and not saved["outside"], "B2可见布局溢出")
    require(sample["counts"]["imageFills"] == 0, "必须为原生可编辑界面")
    require(any(v["label"] == sample["named_version"] for v in saved["versions"]), "B2命名版本缺失")
    boards = {b["shapeId"]: b for b in sample["screens"]}
    controls = {c["shapeId"]: c for c in sample["controls"]}
    require(set(boards) == {b["shapeId"] for b in saved["screens"]}, "B2页面UUID改变")
    require(set(controls) == {c["shapeId"] for c in saved["controls"]}, "B2控件UUID改变")
    require({b["shapeId"] for b in previous["screens"]} <= boards.keys(), "B1原页面丢失")
    require({c["shapeId"] for c in previous["controls"]} <= controls.keys(), "B1原控件丢失")
    require(
        {c["id"] for c in sample["components"]} == {c["id"] for c in previous["components"]},
        "原组件改变",
    )
    require(sample["tokenSets"] == saved["tokenSets"], "Token回读不一致")
    require(sum(t["count"] for t in sample["tokenSets"]) == 33, "既有Token数量改变")
    require(not any(c["stableId"] == "M1-B09" for c in controls.values()), "禁止通用恢复入口")
    for screen in screens["planned_screens"]:
        if screens["authorization_scope"] == "C2-B3":
            continue  # 当前映射由check_b3检查；本函数保留B2历史证据核对。
        if not screen["penpot"]:
            continue
        require(screen["implementation_status"] == "not_implemented", "设计不是业务实现")
        require(
            boards[screen["penpot"]["shape_id"]]["stableId"] == screen["id"], "当前screen映射错误"
        )
    for event in interactions["planned_interactions"]:
        for instance in event.get("penpot_instances", []):
            if instance["revision"] != sample["revision"]:
                continue
            c = controls[instance["shape_id"]]
            require(
                c["stableId"] == event["control_id"] and c["eventId"] == event["id"],
                "当前控件/事件映射错误",
            )
    for c in controls.values():
        require(
            c["interactions"] or c["disabled"] == "platform_capacity_pending",
            "动作缺失且未声明禁用",
        )
        for a in c["interactions"]:
            require(
                a["destination"] in {b["shapeId"] for b in saved["rootOrder"]}
                or a["type"] == "close-overlay",
                "原型目标不存在",
            )
    disabled = [c for c in controls.values() if c["disabled"]]
    require(
        len(disabled) == 4 and all(not c["interactions"] for c in disabled),
        "容量待验收卡片不得直接决定",
    )
    require(
        {c["stableId"] for c in disabled} == {"M1-B02", "M1-B03", "M1-B04", "M1-B05"},
        "卡片两类决定缺少禁用闸门",
    )
    old_narrow = read(UX / "evidence/c2-b1b/after-reload-read.json")["narrow"]
    require(saved["narrow"] == old_narrow, "完整SKU清单/数量/计划发生变化")
    for gate in sample["card_auth_gates"]:
        require(
            gate["gateShapeId"] in boards and boards[gate["gateShapeId"]]["stableId"] == "M1-S01",
            "深链缺鉴权入口",
        )
        require(boards[gate["webId"]]["planId"] == gate["planId"], "转Web不是同一计划")
    roles = {v["role"]: v["shape_id"] for v in read(UX / "evidence/c2-b2/role-map.json")}
    require(len(roles) == 8, "四角色与兼任覆盖缺失")
    dangerous = {"M1-B02", "M1-B03", "M1-B04", "M1-B05", "M1-B07", "M1-B08", "M1-B26", "M1-B27"}
    for role in ["operator", "admin", "unauthorized", "admin + operator"]:
        b = boards[roles[role]]["bounds"]
        local = [
            c
            for c in controls.values()
            if b["x"] <= c["bounds"]["x"] < b["x"] + b["width"]
            and b["y"] <= c["bounds"]["y"] < b["y"] + b["height"]
        ]
        require(not any(c["stableId"] in dangerous for c in local), "无决定角色出现业务决定入口")
    role_observations = read(UX / "evidence/c2-b2/role-observations.json")
    narrow = read(UX / "evidence/c2-b2/narrow-observations.json")
    require(
        len(role_observations) == 8 and all(r["passed"] for r in role_observations),
        "身份实点未通过",
    )
    require(
        len(narrow) == 6
        and all(
            n["passed"] and n["viewport"]["width"] == 390 and n["actualFrame"] in n["observed"]
            for n in narrow
        ),
        "390帧身份或负向检查未通过",
    )
    require(len(events) == summary["attempts"], "实测尝试计数不符")
    require(
        sum(e["passed"] for e in events) == summary["clicks_dispatched_and_asserted"],
        "成功点击计数不符",
    )
    for failed, recheck in summary["failure_rechecks"].items():
        require(
            not events[int(failed) - 1]["passed"] and events[recheck - 1]["passed"],
            "失败未保留或未复验",
        )
    require(
        all(e["passed"] for e in events[83:94]) and events[95]["passed"],
        "最终关键窄屏/飞书转Web路径未通过",
    )
    print("M1 B2：当前UUID/禁用卡片/完整清单/角色与390实点一致；真实后端及飞书未验收")


def check_b3(screens, interactions):
    """核对B3当前映射、受限控件和持久版本；不将Viewer当作真实业务验收。"""
    sample = read(UX / "evidence/c2-b3/design-map.json")
    saved = read(UX / "evidence/c2-b3/after-reload-read.json")
    previous = read(UX / "evidence/c2-b2/design-map.json")
    require(screens["authorization_scope"] == "C2-B3", "缺B3明确授权")
    require(sample["revision"] == saved["revision"] == "m1-ui/0.4.0-b3", "B3版本错误")
    require(sample["file"]["id"] == saved["fileId"] == previous["file"]["id"], "正式文件改变")
    require(sample["revn"] == saved["revn"], "B3持久版本不一致")
    persisted = read(UX / "evidence/c2-b3/persisted-version-metadata.json")
    require(persisted["mcp_api_reported_revn"] == saved["revn"], "MCP回报版本记录不一致")
    require(
        persisted["database_persisted_revn"] == sample["persisted_native_revn"]
        and any(
            v["label"] == sample["named_version"]
            and v["persisted_revn"] == sample["persisted_native_revn"]
            for v in persisted["versions"]
        ),
        "缺数据库命名快照持久化核对",
    )
    require(sample["validation"] == saved["validation"] == [], "B3原生校验失败")
    require(not saved["overflow"] and not saved["outside"], "B3可见布局溢出")
    require(sample["counts"]["imageFills"] == 0, "B3必须使用原生对象")
    require(any(v["label"] == sample["named_version"] for v in saved["versions"]), "B3版本缺失")
    boards = {b["shapeId"]: b for b in sample["screens"]}
    controls = {c["shapeId"]: c for c in sample["controls"]}
    require(set(boards) == {b["shapeId"] for b in saved["screens"]}, "B3页面UUID改变")
    require(set(controls) == {c["shapeId"] for c in saved["controls"]}, "B3控件UUID改变")
    require({b["shapeId"] for b in previous["screens"]} <= boards.keys(), "已有页面丢失")
    removed = {c["shapeId"] for c in previous["controls"]} - controls.keys()
    require(removed == {"b806b597-0eb0-80b2-8008-c38740d37e69"}, "仅允许删除重复返回控件")
    require(sample["components"] == previous["components"], "不得创建第二套组件库")
    require(sample["tokenSets"] == previous["tokenSets"], "不得变更既有Token体系")
    require(
        saved["narrow"] == read(UX / "evidence/c2-b2/after-reload-read.json")["narrow"],
        "冻结SKU清单改变",
    )
    targets = {b["shapeId"] for b in saved["rootOrder"]}
    reread = {c["shapeId"]: c for c in saved["controls"]}
    for c in controls.values():
        require(c["interactions"] == reread[c["shapeId"]]["interactions"], "刷新后连接改变")
        require(c["interactions"] or c["disabled"], "缺动作及禁用原因")
        for a in c["interactions"]:
            require(a.get("destination") in targets or a["type"] == "close-overlay", "目标缺失")
        if c["stableId"] in {"M1-B36", "M1-B47", "M1-B32", "M1-B34"}:
            require(not c["interactions"] and c["disabled"], "未确认操作不得模拟业务成功")
    for s in screens["planned_screens"]:
        require(boards[s["penpot"]["shape_id"]]["stableId"] == s["id"], "逻辑页面映射错误")
        require(s["implementation_status"] == "not_implemented", "设计不是实现")
    for e in interactions["planned_interactions"]:
        instances = e.get("penpot_instances", [])
        require(bool(instances) == (e["control_id"] != "M1-B09"), "控件覆盖缺失或恢复入口误启用")
        for i in instances:
            c = controls[i["shape_id"]]
            require(c["eventId"] == e["id"] and c["stableId"] == e["control_id"], "事件映射错误")
    events = read(UX / "evidence/c2-b3/prototype-ui-events.json")["events"]
    require(sum(e["action"] == "click" and e["passed"] for e in events) >= 50, "B3实点记录不足")
    for label in [
        "关闭解释，返回报告",
        "查看 report v0（Mock）",
        "打开下一周期草稿",
        "查看只读管理说明",
        "关联回复 · 待 BC02 确认",
    ]:
        require(any(e.get("label") == label and e["passed"] for e in events), "关键实点缺失")
    print("M1 B3：18逻辑页面、46可渲染事件、当前UUID/禁用合同与实际Viewer证据一致；候选待外审")


def check_final_freeze(screens, interactions):
    """核对本轮局部修订及重载/数据库证据；保留历史 B3 检查。"""
    evidence = UX / "evidence/m1-ux-final"
    saved = read(evidence / "after-reload-read.json")
    current = read(evidence / "design-map.json")
    before = read(evidence / "before-read.json")
    persisted = read(evidence / "after-persisted.json")
    nav = read(evidence / "nav-after.json")
    require(
        current["revision"] == saved["revision"] == screens["m1_visual_revision"], "最终版本错误"
    )
    require(saved["revn"] == persisted["persisted_revn"] == current["revn"], "重载版本不一致")
    require(
        any(
            v["label"] == current["named_version"] and v["revn"] == saved["revn"]
            for v in persisted["versions"]
        ),
        "命名快照不一致",
    )
    require(
        current["screens"] == saved["screens"] and current["controls"] == saved["controls"],
        "当前映射不是重载回读",
    )
    for key in [
        "controls",
        "components",
        "tokenSets",
        "counts",
        "narrow",
        "flows",
        "rootOrder",
        "fontSizes",
    ]:
        require(saved[key] == before[key], "本轮不得扩展或重连既有内容: " + key)
    require(saved["validation"] == saved["overflow"] == saved["outside"] == [], "原生校验/布局失败")
    s08 = "b0616bef-0815-8023-8008-c39894562145"
    require(
        {s["shapeId"] for s in saved["screens"]} == {s["shapeId"] for s in before["screens"]},
        "页面UUID改变",
    )
    require(
        [s["shapeId"] for s, b in zip(saved["screens"], before["screens"], strict=True) if s != b]
        == [s08],
        "只允许 S08 元数据修订",
    )
    selected = next(n for n in nav["nav"] if n["name"] == "M1-C01 / nav-operations")
    require(
        selected["id"] == "b0616bef-0815-8023-8008-c3989480042f"
        and selected["text"] == "运维说明"
        and not selected["hidden"],
        "运维选中态错误",
    )
    require(
        all(
            n["hidden"] and not n["interactions"]
            for n in nav["nav"]
            if n["name"] in {"M1-C01 / nav-approval", "M1-C01 / nav-items"}
        ),
        "admin默认业务导航",
    )
    events = {e["control_id"]: e for e in interactions["planned_interactions"]}
    require(
        events["M1-B30"]["id"] == "M1-E30" and events["M1-B30"]["target_screen"] == "M1-S08",
        "管理入口必须 B30/E30",
    )
    require(
        events["M1-B31"]["label"] == "返回有权首页"
        and events["M1-B31"]["business_action"] == "none",
        "B31返回语义改变",
    )
    for e in events.values():
        require(e["implementation_status"] == "not_implemented", "原型不是业务实现")
    require(len(screens["planned_screens"]) == 18 and len(events) == 47, "逻辑范围改变")
    for screen in screens["planned_screens"]:
        board = next(b for b in saved["screens"] if b["shapeId"] == screen["penpot"]["shape_id"])
        require(
            board["stableId"] == screen["id"] and board["revision"] == screen["penpot"]["revision"],
            "screen与原生版本映射错误",
        )
    ui = read(evidence / "prototype-ui-events.json")["events"]
    require(
        len(ui) == 2
        and all(e["passed"] for e in ui)
        and {e["control"] for e in ui} == {"M1-B30", "M1-B31"},
        "本轮Viewer证据不足",
    )
    doc = (UX / "ux-freeze-candidate.md").read_text()
    require(
        "B30 / E30" in doc and "B31 / E31" in doc and "- B31：当前 admin" not in doc,
        "交接文档入口错误",
    )
    print("最终冻结修订：18逻辑页面、47语义事件、B30/B31、S08原UUID、重载持久版本一致；业务未实现")


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
        if screens.get("m1_visual_revision") in {
            "m1-ui/0.2.0-b1b",
            "m1-ui/0.3.0-b2",
            "m1-ui/0.4.0-b3",
            "m1-ui/0.4.1-freeze-rc",
        }:
            check_b1b(screens, interactions)
            if screens.get("m1_visual_revision") in {
                "m1-ui/0.3.0-b2",
                "m1-ui/0.4.0-b3",
                "m1-ui/0.4.1-freeze-rc",
            }:
                check_b2(screens, interactions)
            if screens.get("m1_visual_revision") in {"m1-ui/0.4.0-b3", "m1-ui/0.4.1-freeze-rc"}:
                check_b3(screens, interactions)
            if screens.get("m1_visual_revision") == "m1-ui/0.4.1-freeze-rc":
                check_final_freeze(screens, interactions)
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
