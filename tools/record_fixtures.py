"""开发用：从真实麦当劳 MCP 录制测试与离线演示用的数据。只调用只读工具。

用法：
  set MCD_MCP_TOKEN=...      (PowerShell: $env:MCD_MCP_TOKEN="...")
  python tools/record_fixtures.py --city 上海 --keyword 人民广场 --time "2026-10-13 19:00"

输出到 tests/fixtures/：营养表、门店、菜单、几个候选套餐的详情、几次计价。
录制前会去掉 traceId；不录制任何与账户相关的数据（券、积分、订单）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mcp_client import MCPClient, original_json  # noqa: E402

OUT = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
READ_ONLY = {"now-time-info", "list-nutrition-foods", "query-nearby-stores", "query-meals",
             "query-meal-detail", "calculate-price", "campaign-calendar"}
COMBOS = ["9900005466", "9900005462", "9900005456", "9900005460", "9900004835"]


def clean(text: str) -> str:
    return re.sub(r'"traceId":"[0-9a-f]+",?', "", text)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--city", default="上海")
    ap.add_argument("--keyword", default="人民广场")
    ap.add_argument("--time", required=True, help="预约时间 yyyy-MM-dd HH:mm（门店当时得在营业）")
    a = ap.parse_args()

    client = MCPClient()

    def call(name, args=None, save=None):
        assert name in READ_ONLY, name
        text = clean(client.call_text(name, args))
        if save:
            (OUT / save).write_text(text, encoding="utf-8")
        return text

    OUT.mkdir(parents=True, exist_ok=True)
    call("list-nutrition-foods", save="nutrition.txt")
    stores = original_json(call("query-nearby-stores", {"beType": 1, "searchType": 2, "city": a.city, "keyword": a.keyword},
                                save="stores.txt"))["data"]
    store = next(s for s in stores if s["businessStartTime"] != "00:00")
    base = {"storeCode": store["storeCode"], "orderType": 1, "beType": 1, "reservationDate": a.time}
    meals = original_json(call("query-meals", base, save="meals.txt"))["data"]["meals"]
    for code in COMBOS:
        if code in meals:
            call("query-meal-detail", {**base, "code": code}, save=f"detail_{code}.txt")
    call("calculate-price", {**base, "items": [{"productCode": "9900005462", "quantity": 1, "roundList": [
        {"round": "1", "comboItemList": [{"code": "1406", "quantity": 1}]},
        {"round": "2", "comboItemList": [{"code": "4437", "quantity": 1}]},
        {"round": "3", "comboItemList": [{"code": "3071", "quantity": 1}]}]}]}, save="price_bs_corn_zero.txt")
    (OUT / "meta.json").write_text(json.dumps({"store": store["storeName"], "storeCode": store["storeCode"],
                                               "reservationDate": a.time}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("已录制到", OUT, sorted(p.name for p in OUT.iterdir()))


if __name__ == "__main__":
    main()
