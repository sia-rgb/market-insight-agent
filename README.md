# Market Dashboard

## 1. 项目概览 (Project Overview)

**目标**：读取每日更新的金融市场 Excel 文件，提取各工作表中的指标与单位，生成面向网页看板的数据文件，并以深色金融终端风格展示每日变化。
**输入 (Input)**：市场数据 `.xlsx` 文件。
**输出 (Output)**：`frontend/data/dashboard_data.json` 与静态网页看板。
**当前状态**：MVP。

### 架构分层
1. **Data 层**：负责 Excel 读取、标准化与事实数据输出。
2. **Dashboard Data 层**：负责基于标准化数据计算日度变化字段。
3. **Frontend 层**：负责静态网页展示，只消费 `dashboard_data.json`。
4. **Legacy Agent 层**：代码保留，默认停用；仅在显式调用旧命令时运行。

### 技术架构图
```text
Input (market-data-auto.xlsx)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Data 层                                                     │
│  └─ data_ingest.py → standardized_market_data.csv            │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Dashboard Data 层                                           │
│  └─ dashboard_data.py → frontend/data/dashboard_data.json     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Frontend 层                                                 │
│  ├─ frontend/index.html                                      │
│  ├─ frontend/styles.css                                      │
│  └─ frontend/app.js                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 快速开始 (Quick Start)

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 生成看板数据
```bash
python -m src.main run_all --input market-data-auto.xlsx
```

等价的显式命令：
```bash
python -m src.main run_dashboard --input market-data-auto.xlsx
```

### 3) 启动网页服务
```bash
python -m http.server 8000 -d frontend
```

浏览器访问：
```text
http://127.0.0.1:8000
```

---

## 3. 真源表 (Source of Truth)

| 主题 | 唯一真源 |
| :--- | :--- |
| 项目范围、标准化输出与看板展示约束 | `config/project_contract.yaml` |
| 默认执行链路与 Agent 停用边界 | `config/pipeline_contract.yaml` |
| Ingest 配置真源说明 | `config/sheet_contracts.yaml` |
| 日度看板数据构建 | `src/dashboard_data.py` |
| 网页展示入口 | `frontend/index.html` |
| 模块装配与 CLI | `docs/dev/implementation_spec.md` |
| 运维与排障 | `docs/ops/runbook_ops.md` |

### 文档地图

| 文档 | 用途 |
| :--- | :--- |
| `config/project_contract.yaml` | 定义当前项目范围、输出对象与禁止行为。 |
| `config/pipeline_contract.yaml` | 定义默认 `run_all` 步骤。 |
| `config/sheet_contracts.yaml` | 定义每个 Excel 工作表的指标字段和单位规则。 |
| `docs/dev/implementation_spec.md` | 定义模块映射、CLI 与开发顺序。 |
| `docs/ops/runbook_ops.md` | 定义运行与排障记录要求。 |

---

## 4. 当前默认链路

```text
market-data-auto.xlsx
  → artifacts/standardized_market_data.csv
  → frontend/data/dashboard_data.json
  → frontend 静态看板
```

默认链路不执行：
- Agent Judgment。
- LLM 调用。
- Tavily 或其他外部检索。
- 周度异常判断。
- Word 周报渲染。

旧 Agent 相关命令仍保留，用于显式兼容：
```bash
python -m src.main run_weekly_calc --input artifacts/standardized_market_data.csv --out-dir artifacts
python -m src.main run_anomaly_detect --input artifacts/weekly_changes.csv --out artifacts/anomaly_candidates.csv
python -m src.main run_insight_generate --changes artifacts/weekly_changes.csv --candidates artifacts/anomaly_candidates.csv --out artifacts/report_insights.json --no-enable-external-search
python -m src.main run_render_report --insights artifacts/report_insights.json --docx outputs/weekly_report.docx
```

---

## 5. 资产类型

**数据频率**：日更

| 资产大类 | 具体资产类型 | 具体指标 |
| :--- | :--- | :--- |
| **权益** | 全球股指 | 最新收盘价、最近一周、最近1月、2026年至今、2025年全年 |
| **权益** | A股交易量 | 上证指数成交额、深证成指成交额、A股总成交额 |
| **权益** | 南北向 | 沪股通-成交净买入、港股通-成交净买入、深股通-成交净买入、南向-成交净买入 |
| **权益** | 两融余额 | 买入额占A股成交额、融资融券余额、两融余额占A股流通市值、融资余额、融券余额、两融交易额、两融交易额占A股成交额、融资买入额、融资卖出额 |
| **权益** | VIX | 收盘价 |
| **权益** | 散户情绪资金流向 | 大单净流入额、中单净流入额、小单净流入额、散户交易金额 |
| **固收** | 债券指数 | 中债-综合全价(总值)指数、中债-投资级中资美元债全价(总值)指数 |
| **固收** | 债券收益率 | 中债国债到期收益率:10年、美国:国债收益率:10年 |
| **固收** | DR001收盘价 | 收盘价 |
| **固收** | 同业拆借利率 | 美元LIBOR隔夜收盘价、SHIBOR隔夜收盘价 |
| **外汇** | 美元指数&人民币汇率 | 美元指数收盘价、美元中间价收盘价 |
| **大宗商品** | 石油价格 | EDBclose |
| **大宗商品** | 黄金价格 | EDBclose |
| **衍生品** | 50ETF期权 | 日成交量、日认购成交量、日认沽成交量、日认沽/认购、日持仓量、日认购持仓量、日认沽持仓量 |
