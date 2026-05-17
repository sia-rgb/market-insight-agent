
## 1. 项目概览 (Project Overview)

**目标**：构建一个以 Agent 异常分析为核心的日度市场数据洞察看板。系统基于每日更新的多资产市场数据，先由 Data 层提供标准化、不可篡改的日度事实底座，再由 Agent 层识别重点异常、生成审慎解释并补充外部线索，最终通过前端看板展示分析结果，并支持导出长图用于汇报与复盘。
**输入 (Input)**：市场数据 `.xlsx` 文件。
**输出 (Output)**：Agent 异常分析结果 `frontend/data/agent_insights.json`、看板数据底座 `frontend/data/dashboard_data.json`、静态网页看板 `frontend/` 与可导出的看板长图。
**当前状态**：MVP。Data 层与看板展示链路已形成可运行闭环；Agent 异常分析是项目主线能力，当前通过显式命令生成结果并在看板中展示。

### 架构分层
1.  **Data 层**：负责读取日度市场数据、标准化字段、计算基础日度变化，提供事实底座；不做主观归因。
2.  **Agent 层**：负责围绕异常数据进行筛选、解释生成、外部线索补充与审慎归因，是当前项目的核心业务能力。
3.  **Frontend / Dashboard 层**：负责承载 Agent 异常分析结果与基础日度监测结果，提供筛选、趋势展示、榜单展示和长图导出。
4.  **Legacy Report 层**：保留历史周度异常与 Word 周报相关能力，仅作为显式调用的兼容链路，不作为当前主线。

### 技术架构图
```text
Input (market-data-auto.xlsx)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Data 层：日度事实底座                                       │
│  ├─ data_ingest.py      → standardized_market_data.csv       │
│  └─ dashboard_data.py   → frontend/data/dashboard_data.json  │
│     计算 latest value / previous value / daily change / rank │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Agent 层：异常分析主线                                      │
│  └─ dashboard_agent_insights.py                              │
│     → frontend/data/agent_insights.json                      │
│     异常筛选 / 解释生成 / 外部线索补充 / 审慎归因              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Dashboard 层：最终交付形态                                  │
│  ├─ frontend/index.html                                      │
│  ├─ frontend/app.js                                          │
│  └─ frontend/styles.css                                      │
│     展示 Agent Judgment / 基础监测 / 趋势图 / 榜单 / 长图导出 │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 快速开始 (Quick Start)

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 生成日度看板数据底座
```bash
python -m src.main run_all --input market-data-auto.xlsx
```

### 3) 生成 Agent 异常分析结果
```bash
python -m src.main run_agent_insights --dashboard-data frontend/data/dashboard_data.json --out frontend/data/agent_insights.json
```

Agent 分析结果当前通过显式命令生成，未并入默认 `run_all`。如未配置 `DEEPSEEK_API_KEY`，系统会基于内部数据生成 fallback 解释；如未配置 `SERPER_API_KEY`，外部线索检索会降级为空。

### 4) 启动网页服务
```bash
python -m http.server 8000 -d frontend
```

浏览器访问：
```text
http://127.0.0.1:8000
```

Windows 一键启动脚本 `start_dashboard.bat` 当前会执行日度看板数据生成与网页服务启动；Agent 异常分析仍需使用上方显式命令生成。

---

## 3. 真源表 (Source of Truth)

| 主题 | 唯一真源 |
| :--- | :--- |
| 项目范围、数据频率、看板输出与事实完整性约束 | `config/project_contract.yaml` |
| 默认执行链路与 Agent 显式调用边界 | `config/pipeline_contract.yaml` |
| Ingest 配置真源说明 | `config/sheet_contracts.yaml` |
| 日度看板数据结构与变化字段计算 | `src/dashboard_data.py` |
| Agent 异常分析结果生成 | `src/dashboard_agent_insights.py` |
| LLM 解释与外部线索检索 | `src/agent_llm.py` + `src/agent_tools.py` |
| 前端看板展示与长图导出 | `frontend/index.html` + `frontend/app.js` + `frontend/styles.css` |
| 全球股指标准化表现配置 | `config/global_index_performance.yaml` |
| Agent 指标语义词典 | `config/indicator_dictionary.yaml` |
| Legacy 周度异常规则参数与映射 | `config/rules_config.yaml` + `config/metric_rule_mapping.yaml` |
| Legacy 周报输出对象契约 | `schemas/report_insights.schema.json` |

---

## 4. 资产类型

**数据频率**：日更

下表为 Data 层日度事实底座的资产覆盖范围，用于支撑 Agent 异常分析和看板展示。

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

---

## 5. 资产异动判断逻辑

当前主线以 Agent 异常分析为核心，日度变化字段和榜单为异常筛选提供事实基础。

### 1) Data 层：生成可分析事实
基于标准化后的日度市场数据生成：
- 最新值。
- 前值。
- 日度绝对变化。
- 日度变化率。
- 方向标识。
- 涨幅、跌幅与绝对变化榜单。

Data 层只产出事实，不生成主观归因，不改写原始数值。

### 2) Agent 层：筛选重点异常
Agent 当前从 `dashboard_data.json` 中读取日度变化和榜单数据，优先选择绝对变化幅度较大的记录作为异常分析对象。

当指定 `--target-date` 时，Agent 会基于该日期的全量序列记录重新筛选异常对象；未指定日期时，默认使用看板当前有效收盘日的榜单结果。

### 3) Agent 层：生成解释与外部线索
对每条异常记录，Agent 会构造包含资产、指标、方向、日期的市场检索问题，并结合内部数据事实生成：
- 异常方向与幅度描述。
- 可能驱动因素。
- 外部参考线索。
- 证据摘要。
- 置信度提示。

外部线索只作为可能解释，不构成直接因果证明。

### 4) Dashboard 层：展示异常洞察
前端看板读取 `agent_insights.json` 后展示 Agent Judgment 区块，同时保留基础日度监测、趋势图、榜单和长图导出能力。

### 5) Legacy 周度异常规则
历史阈值、Fallback 固定阈值、Robust Z-Score、横向排名和分位类规则仍保留在 legacy 周度命令中，仅在显式调用 `run_weekly_calc`、`run_anomaly_detect`、`run_insight_generate`、`run_render_report` 时使用，不属于当前默认主线。