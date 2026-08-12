#!/usr/bin/env python3
"""
Loupe QIC 数据同步服务
从字节跳动 Loupe 质检系统拉取订单数据，写入本地 SQLite

用法:
    python sync_service.py --test              # 测试 API 连接
    python sync_service.py --mode full          # 全量同步
    python sync_service.py --mode incremental   # 增量同步（只拉新增）
    python sync_service.py --fetch-order QC001  # 拉取单条订单
"""

import sys
# Windows 控制台默认 GBK 编码，无法输出 emoji（📋✅❌等），会导致 print 抛异常中断，
# 同步进程可能因此中止、数据写不进数据库。强制 stdout/stderr 使用 UTF-8。
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import logging
import sqlite3
import time

logger = logging.getLogger("qc_server.sync")
import sys
import random
from pathlib import Path
from datetime import datetime
from urllib.parse import urljoin

import re
import requests

# 导入 QC 引擎（项目根目录）
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

BASE_DIR = Path(__file__).parent


class SyncEngine:
    """Loupe 数据同步引擎"""

    def __init__(self, config_path: str = None, enable_qc: bool = True):
        if config_path is None:
            config_path = BASE_DIR / "config_sync.json"
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = json.load(f)

        self.loupe = self.config["loupe"]
        self.base_url = self.loupe["base_url"].rstrip("/")
        self.session = requests.Session()

        # 设置认证
        cookie = self.loupe.get("auth", {}).get("cookie", "")
        if cookie:
            self.session.headers["Cookie"] = cookie
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)",
            "Accept": "application/json",
            "Referer": self.base_url,
        })

        # 初始化数据库
        db_path = self.config.get("database", {}).get("path", "../data/qic_quality.db")
        if not Path(db_path).is_absolute():
            db_path = str(BASE_DIR / db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db_path = db_path
        self._ensure_tables()

        # 初始化 QC 引擎和通知（同步完立刻审查）
        self.enable_qc = enable_qc
        self.qc_service = None
        self.notifier = None
        self.db_client = None
        if enable_qc:
            try:
                from qc_service import QCService
                from notifier import Notifier
                from db import Database

                # 加载 QC Server 配置
                qc_config_path = BASE_DIR / "config.json"
                with open(qc_config_path, "r", encoding="utf-8") as f:
                    qc_config = json.load(f)

                self.qc_service = QCService()
                self.notifier = Notifier(qc_config)
                self.notifier.start()
                self.db_client = Database()
                print("[QC] 规则引擎已就绪，将在同步后自动审查")
            except Exception as e:
                print(f"[QC] 初始化失败，跳过同步后审查: {e}")
                self.enable_qc = False

    def _get_db(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_tables(self):
        """创建数据库表"""
        conn = self._get_db()
        # 读 schema
        schema_path = BASE_DIR.parent / "data" / "schema.sql"
        if schema_path.exists():
            conn.executescript(schema_path.read_text("utf-8"))
        conn.commit()
        conn.close()

    # ==================== API 调用 ====================

    def test_connection(self) -> bool:
        """测试 API 连接"""
        print(f"测试连接: {self.base_url}")
        try:
            api_info = self.loupe.get("apis", {}).get("order_search", {})
            path = api_info.get("path", "/")
            method = api_info.get("method", "GET").upper()

            url = urljoin(self.base_url, path)

            if method == "POST":
                resp = self.session.post(url, json={"page": 1, "page_size": 1}, timeout=15)
            else:
                resp = self.session.get(url, params={"page": 1, "page_size": 1}, timeout=15)

            if resp.status_code == 200:
                print(f"✅ API 连接成功 (HTTP {resp.status_code})")
                data = resp.json()
                total = self._get_total(data)
                print(f"   响应结构: {list(data.keys())[:5]}")
                print(f"   总记录数: {total}")
                return True
            elif resp.status_code == 401 or resp.status_code == 403:
                print(f"❌ 认证失败 (HTTP {resp.status_code})，Cookie 可能已过期")
                return False
            else:
                print(f"⚠️  HTTP {resp.status_code}: {resp.text[:200]}")
                return False
        except Exception as e:
            print(f"❌ 连接失败: {e}")
            return False

    def _fetch_page(self, page: int) -> list:
        """拉取一页数据（基于 API接口文档.md）"""
        api_info = self.loupe.get("apis", {}).get("order_search", {})
        path = api_info.get("path", "/api/quality/loupe/inspection/order/list")
        page_size = self.loupe.get("pagination", {}).get("page_size", 50)

        url = urljoin(self.base_url, path)

        # 请求参数（来自 API 文档）
        search_params = self.loupe.get("search_params", {})
        body = {
            "page": page,
            "pageSize": page_size,
            "checkType": search_params.get("checkType", 1),
        }
        # 时间范围过滤（可选）
        t_start = search_params.get("inspectionBatchStartTime", 0)
        t_end = search_params.get("inspectionBatchEndTime", 0)
        if t_start:
            body["inspectionBatchStartTime"] = t_start
        if t_end:
            body["inspectionBatchEndTime"] = t_end

        try:
            resp = self.session.post(url, json=body, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            return self._extract_list(data)
        except Exception as e:
            print(f"  [第{page}页] 请求失败: {e}")
            return []

    def _fetch_detail(self, order_code: str) -> dict:
        """拉取单条订单详情"""
        api_info = self.loupe.get("apis", {}).get("order_detail", {})
        path = api_info.get("path", "/")
        method = api_info.get("method", "GET").upper()
        url = urljoin(self.base_url, path)

        try:
            if method == "POST":
                resp = self.session.post(url, json={"order_code": order_code}, timeout=15)
            else:
                resp = self.session.get(url, params={"order_code": order_code}, timeout=15)
            resp.raise_for_status()

            data = resp.json()
            # 尝试从响应中提取单条记录
            if isinstance(data, dict):
                if "data" in data:
                    return data["data"] if isinstance(data["data"], dict) else {}
                return data
            return {}
        except Exception as e:
            print(f"  详情请求失败: {e}")
            return {}

    def _get_total(self, data: dict) -> int:
        """从响应中提取总数（Loupe API: data.pageInfo.count）"""
        try:
            return int(data.get("data", {}).get("pageInfo", {}).get("count", 0))
        except (TypeError, ValueError):
            return 0

    def _extract_list(self, data: dict) -> list:
        """从响应中提取列表（Loupe API: data.list[]）"""
        return data.get("data", {}).get("list", [])

    def _has_more(self, data: dict, current_page: int) -> bool:
        """判断是否还有下一页"""
        total = self._get_total(data)
        page_size = self.loupe.get("pagination", {}).get("page_size", 50)
        if total > 0:
            return current_page * page_size < total
        return False

    # ==================== 同步逻辑 ====================

    def sync_full(self) -> int:
        """全量同步"""
        print("开始全量同步...")
        return self._sync()

    def sync_incremental(self) -> int:
        """增量同步（每次同步前清空？不，只拉最新的）"""
        print("开始增量同步...")
        return self._sync(max_pages=10)  # 增量只拉最近 10 页

    def _sync(self, max_pages: int = None) -> int:
        """核心同步逻辑"""
        total_saved = 0
        all_new_orders = []  # 本次同步的所有新订单
        page = 1
        base_delay = self.loupe.get("pagination", {}).get("delay_ms", 1000) / 1000

        while True:
            if max_pages and page > max_pages:
                break

            print(f"  拉取第 {page} 页...", end=" ")
            items = self._fetch_page(page)

            if not items:
                print("空")
                break

            saved, new_orders = self._save_orders(items)
            total_saved += saved
            all_new_orders.extend(new_orders)
            print(f"{saved} 条", end="")

            page += 1
            if len(items) < self.loupe.get("pagination", {}).get("page_size", 50):
                print(" (最后页)")
                break

            print()
            time.sleep(base_delay)

        print(f"\n同步完成，共保存 {total_saved} 条订单")
        print(f"其中新增 {len(all_new_orders)} 条")

        # 同步完立刻跑 QC 审查
        if all_new_orders and self.enable_qc:
            self._run_qc_on_new_orders(all_new_orders)

        return total_saved

    def _save_orders(self, items: list) -> tuple:
        """保存订单到数据库，返回 (保存数, 新增订单列表)"""
        conn = self._get_db()
        saved = 0
        new_orders = []

        # 第一次保存时检测 API 字段格式
        if items and not hasattr(self, '_field_mode_detected'):
            self._detect_field_mode(items[0])

        for item in items:
            try:
                order_code = item.get("订单码", item.get("orderCode", ""))
                if not order_code:
                    order_code = item.get("order_code", "")

                # 如果 API 返回中文列名，无需映射；否则做驼峰→中文映射
                mapped = item if self._api_uses_chinese else self._map_fields(item)
                mapped = self._validate_qc_fields(mapped, order_code)

                # 检查是否已存在
                existing = conn.execute(
                    "SELECT 订单码 FROM qic_orders WHERE 订单码 = ?", (order_code,)
                ).fetchone()

                if existing:
                    # 订单已存在 → UPDATE 更新字段，删除旧检测结果触发重新检测
                    set_clause = ",".join([f"{c}=?" for c in mapped.keys()])
                    conn.execute(
                        f"UPDATE qic_orders SET {set_clause} WHERE 订单码 = ?",
                        list(mapped.values()) + [order_code],
                    )
                    conn.execute("DELETE FROM qc_check_results WHERE order_code = ?", (order_code,))
                else:
                    # 新订单 → INSERT
                    columns = list(mapped.keys())
                    placeholders = ",".join(["?"] * len(columns))
                    conn.execute(
                        f"INSERT INTO qic_orders ({','.join(columns)}) VALUES ({placeholders})",
                        list(mapped.values()),
                    )
                    new_orders.append(mapped)
                saved += 1

            except Exception as e:
                print(f"\n  [保存失败: {order_code}] {e}")

        conn.commit()
        conn.close()
        return saved, new_orders

    def _detect_field_mode(self, sample: dict):
        """检测 API 返回结构（顶层 + 嵌套），打印字段覆盖情况"""
        print(f"\n📋 API 字段检测")
        print(f"   顶层字段: {[k for k in sample.keys() if not isinstance(sample.get(k), dict)][:10]}")
        print(f"   嵌套对象: {[k for k in sample.keys() if isinstance(sample.get(k), dict)]}")

        mapped = self._map_fields(sample)
        required = {"商品名称", "商品材质", "质检结果", "重量", "备注"}
        missing = required - set(mapped.keys())

        if missing:
            print(f"   ⚠️  关键字段缺失: {missing}")
        else:
            print(f"   ✅ 所有关键字段映射正常")
            print(f"   样例: 商品名称={mapped.get('商品名称','')[:20]}, "
                  f"重量={mapped.get('重量','')}, 质检结果={mapped.get('质检结果','')}")

        # API 是嵌套结构，不是中文字段直出
        self._api_uses_chinese = False
        self._field_mode_detected = True

    @staticmethod
    def _extract_sku_weight(item: dict) -> str:
        """从 SKU 描述中提取克重，标准化为 'Xg' 格式"""
        product_info = item.get("productInfo", {})
        sku_list = product_info.get("skuSpecDesc", [])
        for sk in sku_list:
            val = str(sk.get("value", ""))
            # 只提取"约"或"大约"后面的克重，避免误匹配
            match = re.search(r'(?:约|大约)\s*(\d+(?:\.\d+)?)\s*[g克]', val)
            if match:
                return f"{match.group(1)}g"
        return ""

    def _validate_qc_fields(self, data: dict, order_code: str) -> dict:
        """确保 QC 规则所需的字段至少存在（值为空也行）"""
        required_fields = [
            "商品名称", "商品材质", "商品质量", "SKU质量", "重量", "镶嵌材质", "配件材质",
            "质检结果", "宝玉石结论", "贵金属结论", "备注", "饰品类型", "状态",
            "订单码",
        ]
        if "订单码" not in data:
            data["订单码"] = order_code

        missing = [f for f in required_fields if f not in data]
        if missing and not hasattr(self, '_missing_fields_warned'):
            print(f"\n⚠️  API 返回数据缺少以下 QC 字段（将用空值填充）:")
            print(f"   {missing}")
            print(f"   QC 审查结果可能受影响，请检查字段映射")
            self._missing_fields_warned = True

        for f in missing:
            data[f] = ""
        return data

    def _run_qc_on_new_orders(self, orders: list):
        """对新增订单运行规则审查，异常则通知"""
        print(f"\n{'='*50}")
        print(f"🔍 开始审查新增订单 ({len(orders)} 条)...")

        results = self.qc_service.check_batch(orders)
        anomalies = [r for r in results if r["status"] == "anomaly"]

        # 保存审查结果到 DB
        save_list = []
        for r in results:
            save_list.append({
                "order_code": r["order_code"],
                "results": r["results"],
                "status": r["status"],
            })
        self.db_client.save_check_results_batch(save_list)

        print(f"审查完成: {len(results)} 条")
        print(f"正常: {len(results) - len(anomalies)} 条")
        print(f"异常: {len(anomalies)} 条")

        if anomalies:
            print(f"\n异常详情:")
            for a in anomalies:
                print(f"  {a['order_code']}: {[x['rule_name'] + '=' + x['value'] for x in a['anomalies']]}")

            # 发送企业微信通知
            print("\n📤 发送异常通知...")
            self.notifier.send_batch_alert(anomalies)

        print(f"{'='*50}\n")

    def _map_fields(self, item: dict) -> dict:
        """字段映射：嵌套 API 响应 → 中文列名（基于 API字段映射_导出表.xlsx）"""
        # API 响应路径 → 导出表中文列名
        # 路径用 "." 分隔嵌套层级
        PATH_MAP = [
            # === 顶层字段 ===
            ("orderCode",          "订单码"),
            ("certificationCode",  "证书编码"),
            ("inspectionBatchId",  "质检批次号"),
            ("inboundBatchTaskId", "入库批次号"),
            ("pallectCode",        "货盘编号"),
            ("inspectionBatchCreateTime", "批次生成时间"),
            ("inspectionExecFinishTime",   "质检完成时间"),
            ("inspectionRecheckFinishTime","复核完成时间"),
            ("inspectionResultFinishTime", "制证完成时间"),
            ("status",             "状态"),
            ("shopId",             "店铺id"),
            ("shopName",           "店铺名称"),
            ("orderId",            "订单编号"),
            ("unitPrice",          "质检价格"),
            ("isReInspection",     "是否复检"),
            ("inspectionResultName","检测结果"),
            ("checkName",          "操作人"),
            ("operationName",      "操作人"),
            ("qrCode",             "证书链接"),
            # === productInfo 嵌套 ===
            ("productInfo.name",           "商品名称"),
            ("productInfo.material",       "商品材质"),
            ("productInfo.mosaicMaterial", "镶嵌材质"),
            ("productInfo.weight",         "商品质量"),
            ("productInfo.accessories",    "配件材质"),
            ("productInfo.price",          "商品价格"),
            # === inspectionInfo 嵌套 ===
            ("inspectionInfo.jade_conclusion",    "宝玉石结论"),
            ("inspectionInfo.p_metals",           "贵金属结论"),
            ("inspectionInfo.break_check_result", "瑕疵属性"),
            ("inspectionInfo.tag",                "是否挂签"),
            ("inspectionInfo.weight",             "重量"),
            ("inspectionInfo.note",               "备注"),
            ("inspectionInfo.style",              "饰品类型"),
            ("inspectionInfo.note_two",           "样品状态描述"),
            # === rejectReason 嵌套 ===
            ("rejectReason.rejectCode",   "驳回原因"),
            ("rejectReason.rejectReason", "驳回备注"),
        ]

        # 从嵌套 JSON 中取值
        def _get(obj, path):
            for key in path.split("."):
                if isinstance(obj, dict):
                    obj = obj.get(key)
                else:
                    return None
            return obj

        mapped = {}
        for api_path, cn_name in PATH_MAP:
            val = _get(item, api_path)
            if val is None:
                val = ""
            elif not isinstance(val, str):
                val = str(val)
            mapped[cn_name] = val

        # 计算字段: SKU质量（从 skuSpecDesc 中提取克重）
        sku_weight = self._extract_sku_weight(item)
        mapped["SKU质量"] = sku_weight

        # 计算字段: 质检结果（有驳回 → 不通过，否则 → 通过）
        reject_code = mapped.get("驳回原因", "")
        if reject_code:
            mapped["质检结果"] = "不通过"
        else:
            mapped["质检结果"] = "通过"

        # 计算字段: 是否复检（2=是/1=否）
        is_re = mapped.get("是否复检", "")
        if is_re == "2":
            mapped["是否复检"] = "是"
        elif is_re == "1":
            mapped["是否复检"] = "否"

        # API未返回的字段填空值
        api_missing = ["机构地址", "计量单位", "检测性质", "报告用途", "结果出具形式", "样品贮存要求", "场地"]
        for f in api_missing:
            mapped[f] = ""

        return mapped

    # ==================== 单条订单 ====================

    def fetch_single_order(self, order_code: str) -> bool:
        """拉取单条订单"""
        print(f"拉取订单: {order_code}")
        detail = self._fetch_detail(order_code)
        if not detail:
            print("  未获取到数据")
            return False

        # 确保有订单码
        detail["订单码"] = detail.get("订单码", order_code)
        detail["orderCode"] = detail.get("orderCode", order_code)

        saved = self._save_orders([detail])
        print(f"  保存成功: {saved} 条")
        return saved > 0


def main():
    args = sys.argv[1:]

    if "--test" in args:
        engine = SyncEngine()
        engine.test_connection()
    elif "--mode" in args:
        idx = args.index("--mode")
        mode = args[idx + 1] if idx + 1 < len(args) else "full"
        engine = SyncEngine()
        if mode == "full":
            engine.sync_full()
        elif mode == "incremental":
            engine.sync_incremental()
        else:
            print(f"未知模式: {mode}")
    elif "--fetch-order" in args:
        idx = args.index("--fetch-order")
        code = args[idx + 1] if idx + 1 < len(args) else ""
        if not code:
            print("请提供订单码")
            return
        engine = SyncEngine()
        engine.fetch_single_order(code)
    else:
        print("""
Loupe QIC 数据同步服务

用法:
    python sync_service.py --test              测试 API 连接
    python sync_service.py --mode full          全量同步
    python sync_service.py --mode incremental   增量同步
    python sync_service.py --fetch-order QC001  拉取单条订单

配置: config_sync.json
        """)


if __name__ == "__main__":
    main()
