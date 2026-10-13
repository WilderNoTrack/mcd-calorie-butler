#!/usr/bin/env python3
"""麦麦热量管家 · 计算引擎（纯标准库，Python 3.9+）。

分工：AI 通过麦当劳 MCP 取数（营养表、菜单、套餐详情、计价），把原始返回存成文件交给本脚本；
本脚本负责记账、算剩余热量、算味热比、排餐和套用口味特调。数字一律由代码算，不让模型心算。

数据只存在本机：$MCD_BUTLER_HOME，默认 ~/.mcd-calorie-butler
所有命令输出 JSON（UTF-8）。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PUBLIC_LOVE = HERE.parent / "data" / "public_love.json"
MAIN_MEALS = ("breakfast", "lunch", "dinner")
MEAL_NAMES = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐", "snack": "加餐"}
DEFAULT_SPLIT = {"breakfast": 0.30, "lunch": 0.40, "dinner": 0.30}
ALIASES = {"纯牛奶": "纯牛奶（盒装）", "无糖可乐中杯": "无糖可口可乐中杯", "无糖可乐大杯": "无糖可口可乐大杯",
           "无糖可乐小杯": "无糖可口可乐小杯", "麦辣鸡翅2块": "麦辣鸡翅-2块", "100%苹果汁(盒装)": "100%苹果汁"}


class ButlerError(Exception):
    pass


# ---------------------------------------------------------------- 存储

def home() -> Path:
    p = Path(os.environ.get("MCD_BUTLER_HOME") or Path.home() / ".mcd-calorie-butler")
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def load_profile() -> dict:
    p = read_json(home() / "profile.json", {})
    p.setdefault("goal_kcal", 1800)
    p.setdefault("protein_g", 90)
    p.setdefault("floor_kcal", 1200)
    p.setdefault("mode", "cut")
    p.setdefault("split", dict(DEFAULT_SPLIT))
    p.setdefault("tastes", [])
    p.setdefault("loves", {})
    p.setdefault("learned", {})
    return p


def save_profile(p: dict) -> None:
    write_json(home() / "profile.json", p)


def diary_path(date: str) -> Path:
    return home() / "diary" / f"{date}.json"


def today_str() -> str:
    return dt.date.today().isoformat()


# ---------------------------------------------------------------- MCP 返回解析

def mcp_payload(text: str):
    """官方工具常把 JSON 包在 Markdown 说明后面。取出 {"success":...} 那段；也接受纯 JSON。"""
    text = text.strip()
    start = text.find('{"success"')
    if start < 0 and text.startswith("{"):
        start = 0
    if start < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return None
    if isinstance(obj, dict) and obj.get("success") is False:
        raise ButlerError(f"麦当劳 MCP 返回失败：code={obj.get('code')} {obj.get('message')}")
    return obj


def read_source(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8")


def parse_nutrition(text: str) -> dict:
    """解析 list-nutrition-foods：data 是 `[160]{productName,...}:` 加逐行 CSV。"""
    obj = mcp_payload(text)
    table = obj["data"] if obj else text
    lines = [l.strip() for l in table.splitlines() if l.strip()]
    if not lines or not lines[0].startswith("["):
        raise ButlerError("看不懂这份营养数据：应来自 list-nutrition-foods 的返回")
    header = re.search(r"\{(.+)\}", lines[0]).group(1).split(",")
    out = {}
    for line in lines[1:]:
        parts = line.split(",")
        if len(parts) < len(header):
            continue
        nums = parts[-(len(header) - 2):]
        name = ",".join(parts[: len(parts) - len(header) + 1])
        row = dict(zip(header[2:], nums))
        try:
            out[name] = {"kcal": int(float(row["energyKcal"])), "protein": float(row["protein"]),
                         "fat": float(row["fat"]), "carb": float(row["carbohydrate"]), "sodium": float(row["sodium"])}
        except (KeyError, ValueError):
            continue
    if not out:
        raise ButlerError("营养数据是空的")
    return out


def norm(name: str) -> str:
    return re.sub(r"[\s·•]", "", name).replace("（", "(").replace("）", ")")


def strip_paren(name: str) -> str:
    return re.sub(r"\(.*?\)", "", norm(name))


class Nutrition:
    def __init__(self, table: dict):
        self.table = table
        self._norm = {norm(k): k for k in table}
        self._bare = {}
        for k in table:
            self._bare.setdefault(strip_paren(k), k)

    def find(self, name: str):
        """按名字找官方营养数据：精确 → 别名 → 去括号。找不到返回 None，绝不猜。"""
        n = norm(name)
        if n in self._norm:
            return self._norm[n]
        alias = ALIASES.get(n) or ALIASES.get(name)
        if alias and norm(alias) in self._norm:
            return self._norm[norm(alias)]
        b = strip_paren(name)
        return self._bare.get(b)

    def get(self, name: str):
        key = self.find(name)
        return (key, self.table[key]) if key else (None, None)


def load_nutrition(required=True):
    cache = read_json(home() / "nutrition.json", None)
    if not cache:
        if required:
            raise ButlerError("还没有营养数据：先调用麦当劳 MCP 的 list-nutrition-foods，把返回存成文件后运行 `butler.py nutrition load 文件`")
        return None, None
    return Nutrition(cache["items"]), cache.get("loaded_at")


# ---------------------------------------------------------------- 爱吃程度与味热比

class Loves:
    def __init__(self, profile: dict):
        data = read_json(PUBLIC_LOVE, {"default": 6.0, "rules": []})
        self.default = float(data.get("default", 6.0))
        self.rules = data.get("rules", [])
        self.user = profile.get("loves", {})
        self.learned = profile.get("learned", {})

    def public(self, name: str):
        for r in self.rules:
            p = r["pattern"]
            if (r["match"] == "exact" and name == p) or (r["match"] == "prefix" and name.startswith(p)) \
                    or (r["match"] == "contains" and p in name):
                return float(r["love"]), "大众口味"
        return self.default, "默认值"

    def of(self, name: str):
        """返回 (爱吃程度, 来源)。用户自己设的优先；其次大众默认值 + 从历史订单学到的加成。"""
        n = norm(name)
        for k, v in self.user.items():
            if norm(k) == n:
                return float(v), "你设置的"
        base, src = self.public(name)
        bonus = 0.0
        for k, v in self.learned.items():
            if norm(k) == n:
                bonus = float(v)
        if bonus:
            return min(10.0, round(base + bonus, 1)), src + "＋常点加成"
        return base, src


def ratio(love: float, kcal: float):
    return None if kcal <= 0 else round(love / (kcal / 100), 2)


# ---------------------------------------------------------------- 口味特调

def parse_taste(phrase: str) -> dict:
    p = phrase.strip()
    for opt in ("去冰", "少冰", "多冰"):
        if opt in p:
            return {"phrase": p, "type": "option", "target": opt}
    m = re.match(r"^(?:去掉?|不要|不加|免|少放?)(.+)$", p)
    if m:
        return {"phrase": p, "type": "remove", "target": m.group(1).strip()}
    raise ButlerError(f"没看懂这条口味：{p}。可以写成「去酸黄瓜」「不要洋葱」「可乐去冰」这样")


def apply_tastes(choice: dict, tastes: list):
    """把用户说过的口味套到这个餐品的官方特调选项上，返回 (modification, 用上的口味)。"""
    mod = choice.get("modification") or {}
    groups = mod.get("items") or []
    if not groups or not tastes:
        return None, []
    values_out, used = [], []
    for g in groups:
        vals = g.get("values") or []
        removable = all(v.get("unselectedKey") for v in vals)
        option_hit = None
        if not removable:
            for t in tastes:
                if t["type"] == "option":
                    option_hit = next((v for v in vals if v.get("name") == t["target"]), None)
                    if option_hit:
                        used.append(t["phrase"])
                        break
        if option_hit:
            values_out.append({"code": option_hit["code"], "key": option_hit["selectedKey"], "quantity": 1})
            continue
        if removable:
            removes = [t for t in tastes if t["type"] == "remove" and any(t["target"] in v.get("name", "") for v in vals)]
            if removes:
                for v in vals:
                    hit = next((t for t in removes if t["target"] in v.get("name", "")), None)
                    if hit:
                        values_out.append({"code": v["code"], "key": v["unselectedKey"], "quantity": 0})
                        if hit["phrase"] not in used:
                            used.append(hit["phrase"])
                    else:
                        values_out.append({"code": v["code"], "key": v["selectedKey"], "quantity": v.get("selectedQuantity", 1) or 1})
    if not used:
        return None, []
    return {"values": values_out}, used


# ---------------------------------------------------------------- 套餐配置

def parse_diff(s) -> float:
    m = re.search(r"([+-])\s*¥?\s*([\d.]+)", str(s or ""))
    if not m:
        return 0.0
    return float(m.group(2)) * (1 if m.group(1) == "+" else -1)


def load_meals(path: str) -> dict:
    obj = mcp_payload(read_source(path))
    if not obj:
        raise ButlerError("看不懂这份菜单：应来自 query-meals 的返回")
    data = obj["data"]
    out = {}
    for code, m in data.get("meals", {}).items():
        try:
            out[code] = {"name": m["name"], "price": float(m.get("currentPrice") or 0)}
        except (TypeError, ValueError):
            continue
    cats = {}
    for c in data.get("categories", []):
        for m in c.get("meals", []):
            cats.setdefault(m["code"], c["name"].replace("\n", ""))
    for code in out:
        out[code]["category"] = cats.get(code, "")
    return out


def load_details(paths) -> dict:
    out = {}
    for p in paths:
        obj = mcp_payload(read_source(p))
        if not obj:
            raise ButlerError(f"看不懂 {p}：应来自 query-meal-detail 的返回")
        d = obj["data"]
        out[d["code"]] = d
    return out


class Combo:
    def __init__(self, detail: dict, price: float, nut: Nutrition, loves: Loves):
        self.code, self.name, self.price = detail["code"], detail["name"], price
        self.rounds = []
        for r in detail.get("rounds", []):
            opts = []
            for c in r.get("choices", []):
                key, n = nut.get(c["name"])
                love, src = loves.of(key or c["name"])
                opts.append({"code": c["code"], "name": c["name"], "nutrition_name": key,
                             "kcal": n["kcal"] if n else None, "protein": n["protein"] if n else None,
                             "love": love, "love_source": src, "diff": parse_diff(c.get("diffPrice")),
                             "default": c.get("isDefault") == 1, "raw": c})
            if opts:
                self.rounds.append({"id": str(r["id"]), "name": r.get("name", ""), "options": opts})

    def default_choice(self) -> tuple:
        return tuple(next((i for i, o in enumerate(r["options"]) if o["default"]), 0) for r in self.rounds)

    def summarize(self, choice: tuple) -> dict:
        items = [self.rounds[i]["options"][j] for i, j in enumerate(choice)]
        unknown = [o["name"] for o in items if o["kcal"] is None]
        return {
            "combo": self, "choice": choice, "items": items,
            "kcal": None if unknown else sum(o["kcal"] for o in items),
            "protein": None if unknown else round(sum(o["protein"] for o in items), 1),
            "love": round(sum(o["love"] for o in items), 2),
            "price": round(self.price + sum(o["diff"] for o in items), 2),
            "unknown": unknown,
            "disliked": [o["name"] for o in items if o["love"] <= 0],
        }

    def all_choices(self):
        def rec(i, acc):
            if i == len(self.rounds):
                yield tuple(acc)
                return
            for j in range(len(self.rounds[i]["options"])):
                yield from rec(i + 1, acc + [j])
        yield from rec(0, [])


def config_key(c: dict) -> tuple:
    return (c["combo"].code, c["choice"])


def slot_changes(base: dict, c: dict) -> list:
    """和老样子相比改了哪几样（按套餐的轮次一一对照）。"""
    if base is None:
        return []
    out = []
    for i, x in enumerate(base["items"]):
        y = c["items"][i] if i < len(c["items"]) else None
        if y is None or x["code"] != y["code"]:
            out.append((x, y))
    return out


def score(c: dict, base, protein_gap: float, protein_weight: float) -> float:
    """在预算内挑配法的打分：爱吃程度为主，补蛋白质加分，改动老样子越多扣分，再轻微偏向热量低、价格低的。"""
    s = c["love"] + protein_weight * min(c["protein"], protein_gap) / 10
    s -= 0.3 * len(slot_changes(base, c))
    return s - 0.002 * c["kcal"] - 0.08 * c["price"]


def search(combos: list, budget: int, base, protein_gap: float, protein_weight: float) -> list:
    ranked = []
    for combo in combos:
        for ch in combo.all_choices():
            c = combo.summarize(ch)
            if c["kcal"] is None or c["disliked"] or c["kcal"] > budget:
                continue
            ranked.append((score(c, base, protein_gap, protein_weight), c))
    ranked.sort(key=lambda x: (-x[0], x[1]["price"]))
    return [c for _, c in ranked]


def explain(base: dict, c: dict) -> list:
    """把老样子到方案的每一处改动讲清楚，按味热比代价从小到大排：每少吃 100 大卡，爱吃程度降多少。"""
    steps = []
    for x, y in slot_changes(base, c):
        saved = x["kcal"] - y["kcal"]
        lost = x["love"] - y["love"]
        cost = round(lost / (saved / 100), 2) if saved > 0 else None
        steps.append({"from": x["name"], "to": y["name"], "saved_kcal": saved, "love_change": round(-lost, 1),
                      "protein_change": round(y["protein"] - x["protein"], 1), "price_change": round(y["diff"] - x["diff"], 2)
                      if c["combo"] is base["combo"] else None, "cost": cost})
    steps.sort(key=lambda s: (s["cost"] is None, s["cost"] if s["cost"] is not None else 0))
    return steps


def singles_fit(meals: dict, combos: list, nut: Nutrition, loves: Loves, budget: int, limit=3) -> list:
    combo_codes = {c.code for c in combos}
    out = []
    for code, m in meals.items():
        if code in combo_codes:
            continue
        key, n = nut.get(m["name"])
        if not n or n["kcal"] <= 0 or n["kcal"] > budget:
            continue
        love, src = loves.of(key)
        if love <= 0:
            continue
        out.append({"code": code, "name": m["name"], "kcal": n["kcal"], "protein": n["protein"], "price": m["price"],
                    "love": love, "love_source": src, "ratio": ratio(love, n["kcal"])})
    out.sort(key=lambda x: (-x["love"], -x["protein"], x["price"]))
    return out[:limit]


def render_config(c: dict, tastes: list) -> dict:
    items, round_list = [], []
    for r, o in zip(c["combo"].rounds, c["items"]):
        mod, used = apply_tastes(o["raw"], tastes)
        entry = {"code": o["code"], "quantity": 1}
        if mod:
            entry["modification"] = mod
        round_list.append({"round": r["id"], "comboItemList": [entry]})
        items.append({"round": r["name"], "code": o["code"], "name": o["name"], "kcal": o["kcal"],
                      "protein": o["protein"], "love": o["love"], "love_source": o["love_source"],
                      "ratio": ratio(o["love"], o["kcal"] or 0) if o["kcal"] is not None else None,
                      "price_diff": o["diff"], "tastes": used})
    return {
        "combo_code": c["combo"].code, "combo_name": c["combo"].name, "items": items,
        "kcal": c["kcal"], "protein": c["protein"], "love": c["love"],
        "price_yuan_estimate": c["price"],
        "calculate_price_items": [{"productCode": c["combo"].code, "quantity": 1, "roundList": round_list}],
    }


# ---------------------------------------------------------------- 预算

def day_summary(profile: dict, date: str) -> dict:
    diary = read_json(diary_path(date), {"date": date, "meals": []})
    eaten = {m: {"kcal": 0, "protein": 0.0, "entries": 0} for m in list(MAIN_MEALS) + ["snack"]}
    for e in diary["meals"]:
        slot = eaten.setdefault(e["meal"], {"kcal": 0, "protein": 0.0, "entries": 0})
        slot["kcal"] += sum(i["kcal"] for i in e["items"])
        slot["protein"] += sum(i.get("protein", 0) for i in e["items"])
        slot["entries"] += 1
    total = sum(v["kcal"] for v in eaten.values())
    protein = round(sum(v["protein"] for v in eaten.values()), 1)
    remaining = profile["goal_kcal"] - total
    open_meals = [m for m in MAIN_MEALS if eaten[m]["entries"] == 0]
    split = profile.get("split", DEFAULT_SPLIT)
    shares = {m: split.get(m, 0.3) for m in open_meals}
    budgets = {}
    for m in open_meals:
        budgets[m] = max(0, round(remaining * shares[m] / sum(shares.values()))) if sum(shares.values()) else 0
    return {
        "date": date, "goal_kcal": profile["goal_kcal"], "eaten_kcal": total, "remaining_kcal": remaining,
        "protein_goal_g": profile["protein_g"], "protein_eaten_g": protein,
        "protein_gap_g": round(max(0, profile["protein_g"] - protein), 1),
        "meals": {m: {"name": MEAL_NAMES.get(m, m), **v} for m, v in eaten.items()},
        "open_meals": open_meals, "meal_budgets": budgets, "log": diary["meals"],
    }


# ---------------------------------------------------------------- 命令

def cmd_profile(a):
    p = load_profile()
    if a.action == "show":
        return {"profile": p}
    notes = []
    for field in ("name", "store_code", "store_name"):
        v = getattr(a, field)
        if v:
            p[field] = v
    if a.mode:
        p["mode"] = a.mode
    if a.weight and a.height and a.age and a.sex:
        bmr = 10 * a.weight + 6.25 * a.height - 5 * a.age + (5 if a.sex == "m" else -161)
        tdee = bmr * (a.activity or 1.375)
        delta = {"cut": -400, "keep": 0, "bulk": 300}[p["mode"]]
        p["floor_kcal"] = int(max(bmr, 1500 if a.sex == "m" else 1200))
        p["goal_kcal"] = int(round(max(tdee + delta, p["floor_kcal"]) / 10) * 10)
        p["protein_g"] = int(round(a.weight * {"cut": 1.6, "keep": 1.2, "bulk": 1.8}[p["mode"]]))
        p["body"] = {"sex": a.sex, "age": a.age, "height": a.height, "weight": a.weight, "activity": a.activity or 1.375}
        notes.append(f"基础代谢约 {int(bmr)} 大卡，日常消耗约 {int(tdee)} 大卡。")
    if a.goal_kcal:
        if a.goal_kcal < p["floor_kcal"]:
            notes.append(f"{a.goal_kcal} 大卡低于安全下限 {p['floor_kcal']} 大卡，已按下限设置。长期吃得太少会掉肌肉、反弹，不建议。")
            p["goal_kcal"] = p["floor_kcal"]
        else:
            p["goal_kcal"] = a.goal_kcal
    if a.protein:
        p["protein_g"] = a.protein
    save_profile(p)
    return {"profile": p, "notes": notes}


def cmd_taste(a):
    p = load_profile()
    if a.action == "add":
        t = parse_taste(a.phrase)
        p["tastes"] = [x for x in p["tastes"] if x["phrase"] != t["phrase"]] + [t]
    elif a.action == "remove":
        p["tastes"] = [x for x in p["tastes"] if x["phrase"] != a.phrase]
    save_profile(p)
    return {"tastes": p["tastes"]}


def cmd_love(a):
    p = load_profile()
    if a.action == "set":
        if not 0 <= a.score <= 10:
            raise ButlerError("爱吃程度是 0～10，0 表示不吃")
        p["loves"][a.name] = a.score
        save_profile(p)
    nut, _ = load_nutrition(required=a.action == "show")
    loves = Loves(p)
    if a.action == "set":
        love, src = loves.of(a.name)
        return {"name": a.name, "love": love, "source": src}
    rows = []
    seen = set()
    for name, n in nut.table.items():
        if name in seen or n["kcal"] <= 0:
            continue
        seen.add(name)
        love, src = loves.of(name)
        rows.append({"name": name, "kcal": n["kcal"], "protein": n["protein"], "love": love, "source": src,
                     "ratio": ratio(love, n["kcal"])})
    rows.sort(key=lambda r: -r["ratio"])
    if a.known_only:
        rows = [r for r in rows if r["source"] != "默认值"]
    return {"note": "味热比 = 爱吃程度 ÷ 每百大卡。0 大卡的饮品不占热量，不参与排序。", "items": rows[: a.top] if a.top else rows}


def cmd_nutrition(a):
    table = parse_nutrition(read_source(a.file))
    write_json(home() / "nutrition.json", {"loaded_at": dt.datetime.now().isoformat(timespec="seconds"), "items": table})
    return {"loaded": len(table), "sample": dict(list(table.items())[:3])}


def cmd_log(a):
    date = a.date or today_str()
    path = diary_path(date)
    diary = read_json(path, {"date": date, "meals": []})
    if a.action == "remove":
        before = len(diary["meals"])
        diary["meals"] = [m for m in diary["meals"] if m["meal"] != a.meal]
        write_json(path, diary)
        return {"removed": before - len(diary["meals"]), "summary": day_summary(load_profile(), date)}
    if a.action == "show":
        return day_summary(load_profile(), date)
    try:
        raw = json.loads(a.items)
    except json.JSONDecodeError:
        raise ButlerError("--items 要是 JSON 数组，例如 '[{\"name\":\"肉包\",\"kcal\":230,\"protein\":9}]'")
    items, unknown = [], []
    nut = None
    for it in raw:
        it = {"name": it} if isinstance(it, str) else dict(it)
        qty = float(it.get("qty", 1))
        if a.source == "mcd" and "kcal" not in it:
            nut = nut or load_nutrition()[0]
            key, n = nut.get(it["name"])
            if not n:
                unknown.append(it["name"])
                continue
            items.append({"name": key, "kcal": round(n["kcal"] * qty), "protein": round(n["protein"] * qty, 1),
                          "qty": qty, "estimated": False, "basis": "官方营养数据"})
        else:
            if "kcal" not in it:
                raise ButlerError(f"{it.get('name')} 缺少 kcal。非麦当劳食物需要先估算热量再记录")
            items.append({"name": it["name"], "kcal": int(it["kcal"]), "protein": float(it.get("protein", 0)),
                          "qty": qty, "estimated": a.source != "mcd", "basis": "AI 估算" if a.source != "mcd" else "官方营养数据"})
    if unknown:
        raise ButlerError("这些麦当劳餐品在官方营养表里查不到：" + "、".join(unknown) + "。可以让用户确认名称，或按估算记录（--source other）")
    if a.replace:
        diary["meals"] = [m for m in diary["meals"] if m["meal"] != a.meal]
    diary["meals"].append({"meal": a.meal, "source": a.source, "items": items, "note": a.note or "",
                           "logged_at": dt.datetime.now().isoformat(timespec="minutes")})
    write_json(path, diary)
    return {"logged": items, "summary": day_summary(load_profile(), date)}


def cmd_today(a):
    return day_summary(load_profile(), a.date or today_str())


def cmd_plan(a):
    profile = load_profile()
    nut, loaded_at = load_nutrition()
    loves = Loves(profile)
    meals = load_meals(a.meals)
    details = load_details(a.details)
    combos = [Combo(d, meals.get(code, {}).get("price", 0.0), nut, loves) for code, d in details.items()]
    combos = [c for c in combos if c.rounds]
    if not combos:
        raise ButlerError("没有可用的套餐详情：先用 query-meal-detail 查几个候选套餐")
    summary = day_summary(profile, a.date or today_str())
    if a.budget_kcal is not None:
        budget = a.budget_kcal
    else:
        budget = summary["meal_budgets"].get(a.meal, max(0, summary["remaining_kcal"]))
    notes = []

    base_code = a.base or (profile.get("base") or {}).get("code")
    base_combo = next((c for c in combos if c.code == base_code), None)
    result = {"meal": MEAL_NAMES.get(a.meal, a.meal), "budget_kcal": budget, "remaining_today_kcal": summary["remaining_kcal"],
              "protein_gap_g": summary["protein_gap_g"], "nutrition_loaded_at": loaded_at}
    base = None
    if base_combo:
        saved_choice = (profile.get("base") or {}).get("choices") or {}
        ch = list(base_combo.default_choice())
        for i, r in enumerate(base_combo.rounds):
            want = saved_choice.get(r["id"])
            for j, o in enumerate(r["options"]):
                if o["code"] == want:
                    ch[i] = j
        base = base_combo.summarize(tuple(ch))
        if base["kcal"] is None:
            notes.append("老样子里有餐品查不到官方营养数据：" + "、".join(base["unknown"]) + "，这次不拿它做对照。")
            base = None
        else:
            result["base"] = {"combo_name": base_combo.name, "items": [o["name"] for o in base["items"]],
                              "kcal": base["kcal"], "price_yuan_estimate": base["price"], "fits": base["kcal"] <= budget}
    elif base_code:
        notes.append("老样子的套餐这次没有查详情，先不做对照；下次把它也用 query-meal-detail 查一下。")

    weight = {"cut": 1.0, "bulk": 1.0, "keep": 0.5}.get(profile.get("mode"), 1.0)
    ranked = search(combos, budget, base, summary["protein_gap_g"], weight)
    if ranked:
        best = base if base and base["kcal"] <= budget else ranked[0]
        result["plan"] = render_config(best, profile["tastes"])
        result["steps"] = explain(base, best) if base else []
        others, seen = [], {best["combo"].code}
        for c in ranked[1:]:
            if c["combo"].code not in seen:
                seen.add(c["combo"].code)
                others.append(render_config(c, profile["tastes"]))
            if len(others) == 2:
                break
        result["options"] = others
        if best is base:
            notes.append("老样子放得下，一样都不用换。options 里是同样放得下的其他配法，想换口味再看。")
    else:
        singles = singles_fit(meals, combos, nut, loves, budget)
        result["singles"] = singles
        lightest = min((c.summarize(ch) for c in combos for ch in c.all_choices()),
                       key=lambda c: c["kcal"] if c["kcal"] is not None else 10 ** 9)
        if lightest["kcal"] is not None:
            result["lightest_combo"] = render_config(lightest, profile["tastes"])
            result["lightest_combo"]["over_kcal"] = lightest["kcal"] - budget
        notes.append("套餐怎么换都放不下这顿的预算。" + ("可以单点，见 singles。" if singles else "单点也放不下。")
                     + "不建议靠饿一顿来抵消，想吃可以按最轻的来，明天再调整。")
    if budget < 300:
        notes.append(f"这顿只剩 {budget} 大卡，今天已经吃得差不多了。")
    result["notes"] = notes
    result["next"] = "把 plan.calculate_price_items 原样作为 items 传给 calculate-price（返回单位是分），核价后再给用户确认。"
    return result


def cmd_price(a):
    obj = mcp_payload(read_source(a.file))
    if not obj:
        raise ButlerError("看不懂这份计价结果：应来自 calculate-price 的返回")
    d = obj["data"]
    yuan = lambda v: None if v is None else round(v / 100, 2)
    return {"unit_note": "calculate-price 的金额单位是分，已换算成元",
            "price_yuan": yuan(d.get("price")), "original_yuan": yuan(d.get("originalPrice")),
            "discount_yuan": yuan(d.get("discount")), "delivery_yuan": yuan(d.get("deliveryPrice")),
            "products": [{"name": p["productName"], "quantity": p["quantity"], "subtotal_yuan": yuan(p.get("subtotal"))}
                         for p in d.get("productList", [])],
            "take_ways": d.get("takeWayList", [])}


def cmd_base(a):
    p = load_profile()
    if a.action == "set":
        choices = json.loads(a.choices) if a.choices else {}
        p["base"] = {"code": a.code, "name": a.name or "", "choices": {str(k): str(v) for k, v in choices.items()}}
        save_profile(p)
    return {"base": p.get("base")}


def cmd_learn(a):
    p = load_profile()
    obj = mcp_payload(read_source(a.file))
    orders = ((obj or {}).get("data") or {}).get("list") or []
    counts, combos = {}, {}
    for o in orders:
        for prod in o.get("orderProductList") or []:
            name = prod.get("productName")
            if name:
                counts[name] = counts.get(name, 0) + prod.get("quantity", 1)
            subs = prod.get("comboItemList") or []
            if subs:
                key = prod.get("productCode")
                combos.setdefault(key, {"name": name, "count": 0, "choices": []})
                combos[key]["count"] += 1
                combos[key]["choices"] = subs
            for s in subs:
                sname = s.get("productName") or s.get("name")
                if sname:
                    counts[sname] = counts.get(sname, 0) + 1
    p["learned"] = {k: round(min(2.0, 0.3 * v), 1) for k, v in counts.items()}
    if combos:
        code, info = max(combos.items(), key=lambda kv: kv[1]["count"])
        p.setdefault("base_candidate", {})
        p["base_candidate"] = {"code": code, "name": info["name"], "count": info["count"]}
    save_profile(p)
    return {"orders": len(orders), "learned": p["learned"], "base_candidate": p.get("base_candidate"),
            "note": "没有历史订单时，就先用大众默认值，等用户确认几次后再学。" if not orders else ""}


def build_parser():
    ap = argparse.ArgumentParser(prog="butler.py", description="麦麦热量管家计算引擎")
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("profile", help="目标热量、蛋白质、门店")
    s.add_argument("action", choices=["show", "set"])
    s.add_argument("--goal-kcal", type=int); s.add_argument("--protein", type=int)
    s.add_argument("--mode", choices=["cut", "keep", "bulk"])
    s.add_argument("--sex", choices=["m", "f"]); s.add_argument("--age", type=int)
    s.add_argument("--height", type=float); s.add_argument("--weight", type=float)
    s.add_argument("--activity", type=float, help="1.2 久坐 / 1.375 轻度 / 1.55 中度 / 1.725 高强度")
    s.add_argument("--name"); s.add_argument("--store-code"); s.add_argument("--store-name")
    s.set_defaults(fn=cmd_profile)

    s = sub.add_parser("taste", help="口味：说一次，以后每单自动带上")
    s.add_argument("action", choices=["add", "remove", "show"]); s.add_argument("phrase", nargs="?", default="")
    s.set_defaults(fn=cmd_taste)

    s = sub.add_parser("love", help="爱吃程度与味热比")
    s.add_argument("action", choices=["show", "set"]); s.add_argument("name", nargs="?")
    s.add_argument("score", nargs="?", type=float); s.add_argument("--top", type=int, default=0)
    s.add_argument("--known-only", action="store_true", help="只看有大众口味数据或你设置过的")
    s.set_defaults(fn=cmd_love)

    s = sub.add_parser("nutrition", help="载入 list-nutrition-foods 的返回")
    s.add_argument("action", choices=["load"]); s.add_argument("file")
    s.set_defaults(fn=cmd_nutrition)

    s = sub.add_parser("log", help="记录吃了什么")
    s.add_argument("action", choices=["add", "remove", "show"])
    s.add_argument("--meal", choices=["breakfast", "lunch", "dinner", "snack"])
    s.add_argument("--source", choices=["mcd", "other"], default="other")
    s.add_argument("--items", default="[]"); s.add_argument("--note"); s.add_argument("--date")
    s.add_argument("--replace", action="store_true", help="覆盖这一餐原来的记录")
    s.set_defaults(fn=cmd_log)

    s = sub.add_parser("today", help="今天吃了多少、还剩多少")
    s.add_argument("--date"); s.set_defaults(fn=cmd_today)

    s = sub.add_parser("plan", help="按味热比排一顿麦当劳")
    s.add_argument("--meal", choices=list(MAIN_MEALS), required=True)
    s.add_argument("--meals", required=True, help="query-meals 的返回文件")
    s.add_argument("--details", nargs="+", required=True, help="query-meal-detail 的返回文件（可多个）")
    s.add_argument("--budget-kcal", type=int); s.add_argument("--base", help="老样子的套餐编码")
    s.add_argument("--date"); s.set_defaults(fn=cmd_plan)

    s = sub.add_parser("price", help="解析 calculate-price 的返回（分 → 元）")
    s.add_argument("file"); s.set_defaults(fn=cmd_price)

    s = sub.add_parser("base", help="老样子")
    s.add_argument("action", choices=["show", "set"]); s.add_argument("--code"); s.add_argument("--name")
    s.add_argument("--choices", help='套餐每轮选什么，如 {"2":"4810","3":"3050"}')
    s.set_defaults(fn=cmd_base)

    s = sub.add_parser("learn", help="从 order-list 的返回学口味")
    s.add_argument("file"); s.set_defaults(fn=cmd_learn)
    return ap


def main(argv=None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = build_parser().parse_args(argv)
    try:
        out = args.fn(args)
        print(json.dumps({"ok": True, **out}, ensure_ascii=False, indent=1))
        return 0
    except ButlerError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False, indent=1))
        return 2


if __name__ == "__main__":
    sys.exit(main())
