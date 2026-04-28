

# Assets Insight Agent

## 1. 项目概览 (Project Overview)

**目标**：将金融市场多资产市场高频动态数据转换为结构化异动洞察与周报页面。
**输入 (Input)**：市场数据 `.xlsx` 文件。
**输出 (Output)**：结构化洞察 `.json` 文件与周报 `.docx` 文件。
**当前状态**：MVP。

### 架构分层
1.  **Data 层**：负责确定性计算与规则判定。
2.  **Agent 层**：负责优先级排序、审慎解释与外部证据补充。
3.  **Render 层**：负责输出 Word 结果。

### 技术架构图
```text
Input (market-data-auto.xlsx)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Data & Analytics 层 (确定性计算，无外部检索)                  │
│  ├─ data_ingest.py         → standardized_market_data.csv   │
│  ├─ data_weekly_calc.py    → weekly_metrics.csv             │
│  │                          → weekly_changes.csv             │
│  └─ data_anomaly_detect.py → anomaly_candidates.csv         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Agent 层 (解释与归纳，允许外部检索)                          │
│  ├─ agent_context.py      → 构造 LLM Context                │
│  ├─ agent_llm.py          → ReAct 循环生成三要点洞察          │
│  ├─ agent_prompt.py       → System Prompt 构建              │
│  ├─ agent_evidence.py     → 引用去重与结构化                 │
│  ├─ agent_tools.py        → Tavily 新闻搜索                  │
│  └─ agent_insight_generate.py → 编排聚合 report_insights     │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Render 层 (纯展示，只消费 report_insights)                  │
│  └─ report_render.py      → weekly_report.docx              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  基础设施                                                   │
│  ├─ main.py                → CLI 入口 & 流水线编排            │
│  ├─ pipeline_contract.py   → Pipeline 配置加载                │
│  ├─ report_schema_contracts.py → JSON Schema 验证            │
│  ├─ data_rules_config.py   → Rules & Metric Mapping 加载      │
│  └─ console_utf8.py        → Windows UTF-8 控制台设置         │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. 快速开始 (Quick Start)

### 1) 安装依赖
```bash
pip install -r requirements.txt
```

### 2) 最短服务启动路径
```bash
python -m http.server 8000 -d frontend
```

### 3) 最短命令行路径
```bash
python -m src.main run_all --input market-data-auto.xlsx
```

---

## 3. 真源表 (Source of Truth)

| 主题 | 唯一真源 |
| :--- | :--- |
| 项目范围、标准化输出与报告展示约束 | `config/project_contract.yaml` |
| 双工作流边界与执行顺序 | `config/pipeline_contract.yaml` |
| Ingest 配置真源说明 | `config/sheet_contracts.yaml` |
| 异常规则参数与映射 | `config/rules_config.yaml` + `config/metric_rule_mapping.yaml` |
| Agent 指标语义词典 | `config/indicator_dictionary.yaml` |
| Agent Judgment 行为约束 | `config/project_contract.yaml` |
| 输出对象契约 | `schemas/report_insights.schema.json` |
| 模块装配与 CLI | `docs/dev/implementation_spec.md` |
| 运维与排障 | `docs/ops/runbook_ops.md` |

---

## 4. 资产类型

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

---

## 5. 资产异动判断逻辑

当前启用 5 类异常规则：

### 1) 历史阈值类 (Adaptive Historical Threshold)
基于历史分布的动态阈值判断：
- 周度涨跌幅 > 过去 52 周 95 分位。
- 金额 / 成交量 / 持仓量变化 > 过去 52 周 90 分位。
- **特点**：自适应市场环境，对不同资产更公平。

### 2) Fallback 固定阈值类 (Fallback Threshold)
当历史样本不足时使用：
- 涨跌幅绝对值 ≥ 5%。
- 比率类指标变化 ≥ 0.2。
- 固收收益率变化 ≥ 0.20 (20bp)。
- **特点**：保底机制，防止“无历史 → 无异常”。

### 3) Robust Z-Score 类
衡量当前变化相对历史分布的异常程度：
- 使用中位数 (Median) 和 MAD (Median Absolute Deviation)。
- 判定条件：偏离 ≥ 3。
- **特点**：抗极端值（比标准差更稳健），捕捉“结构性异常”。

### 4) 横向排名类 (Cross-sectional Ranking)
基于当期横截面排序：
- 全市场波动前 10。
- 同资产类别波动前 3。
- **特点**：捕捉“相对最异常”，不依赖历史。

### 5) 分位类 (Percentile-based)
基于分位数判断：
- 历史分位 ≥ 95%。
- 同类资产横截面分位 ≥ 95%。
- 且同类样本数 ≥ 8。
- **特点**：强调极端位置，兼顾历史与横向比较。