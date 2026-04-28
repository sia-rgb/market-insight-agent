# AGENTS.md

## 1. 行为原则 (Behavior Principles)

- **控制权反转 (Inversion of Control)**：由 Agent 决定何时取数、检索与结束，严禁作为固定流水线的插件使用。
- **证据优先 (Evidence First)**：严禁无证据猜测；所有归因必须追溯至内部事实数据或外部检索证据。
- **事实不篡改 (Fact Integrity)**：严禁改写 Data/Analytics 层产出的任何数值事实。

---

## 2. 双工作流边界 (Workflow Boundaries)

分层职责与边界以 `config/pipeline_contract.yaml` 为唯一真源：

- **工作流 A：确定性流水线 (Data & Analytics)**
  - 职责：仅负责数据读取、标准化、周度计算与规则判定。
  - 禁令：严禁引入外部检索或主观因果推断。
- **工作流 B：智能体循环 (Agent Judgment)**
  - 职责：仅负责优先级排序、解释生成与证据补充。
  - 准则：必须先基于规则层事实，再使用外部证据补充可能的驱动因素 (Possible Drivers)。
- **细节参考**：
  - Agent Judgment 行为契约：见 `config/project_contract.yaml`。
  - 规则白名单：见 `config/rules_config.yaml` 与 `config/metric_rule_mapping.yaml`。

---

## 3. 核心原则 (Core Principles)

- **最小可运行优先 (MVP First)**：优先构建最小可运行版本，所有开发行为必须服务于“功能可运行”。
- **最小改动 (Minimal Change)**：优先选择改动最小的方案，严禁非必要的重构。
- **可运行优先 (Runnable First)**：提交前必须保证核心功能在当前环境下可运行。
- **文档即约束 (Docs as Constraints - [CRITICAL])**：
  - 所有文档均视为运行时硬约束，严禁视为建议或参考。
  - 强制规则：
    - 严禁偏离文档定义的结构或逻辑。
    - 文档冲突必须通过“优先级 (Precedence)”规则解决。
    - 严禁基于经验或常识替代文档定义的明确规则。

---

## 4. 约束分类 (Constraint Categories)

| 类型 | 控制对象 | 本质定义 |
| :--- | :--- | :--- |
| **流程约束 (Process)** | 思考过程 | 思维路径 |
| **行为约束 (Behavior)** | 动作边界 | 能做什么 / 不能做什么 |
| **执行约束 (Execution)** | 触发时机 | 什么时候可以做 |

---

## 5. 流程约束 (Process Constraints)

### 5.1 工作流程 (Workflow)
在开始任何任务前，必须输出结构如下：

1. **最小目标 (Minimal Goal)**：明确本次任务的最小可交付成果 (MVP)。
2. **流程链 (Process Chain)**：使用标准结构表达，如 `Input → Process → Output` 或 `A → B → C`。

> **[注意]**：未经用户显式确认，不得进入代码实现阶段。

---

## 6. 行为约束 (Behavior Constraints)

### 6.1 开发规范 (Development Rules)
- **禁止过早优化**：严禁在 MVP 阶段引入复杂的扩展性设计。
- **优先最小改动**：在实现目标前提下，严禁触碰无关代码。
- **Runnable Check**：提交前必须通过可运行性验证。
- **单行提交**：每次 Commit 必须使用一句话说明改动核心。

### 6.2 禁止行为 (Forbidden Actions)
除非用户明确要求，否则**禁止**：
- 修改日志输出样式或美化 print 内容。
- 重命名变量或修改注释风格。
- 调整无关格式或进行非必要重构。

### 6.3 编码规范 (Encoding Rules - [CRITICAL])
- 所有文件读写必须显式指定 `UTF-8` 编码。
- 严禁依赖系统默认编码。

### 6.4 输出风格 (Output Style)
- 使用结构化表达，保持客观、中立、冷静的语气。
- 避免冗余与重复，优先使用短句，严禁情绪化语言。

---

## 7. 执行约束 (Execution Constraints)

### 7.1 执行前检查 (Preflight Required)
**适用场景**：Benchmark、并发测试、性能实验。

- **必须检查项**：实际约束 (Effective Constraints)、可行性 (Feasibility)、无效条件 (Invalid Conditions)。
- **输出结论**：仅输出 `VALID` 或 `INVALID`。
- **强制规则**：
  - 若结论为 `INVALID`，严禁执行。
  - 严禁假设参数生效，必须经过实际验证。
  - 执行前必须请求用户显式确认。

---

## 8. 文档优先级 (Precedence)

### 8.1 层级矩阵 (Priority Matrix)
当指令或文档冲突时，按以下层级**降序**执行：

1. **Level 0: 最高准则 (The Law) - `AGENTS.md`**
   - 核心：任何行为不得违反本文件定义的“禁止行为”。
2. **Level 1: 直接指令 (Direct Order) - 当前用户 Prompt**
   - 核心：在不违反 L0 的前提下，以用户最新任务目标为准。
3. **Level 2: 全局上下文 (Global Context) - `README.md`**
   - 核心：确保改动符合项目既定架构与业务链路。
4. **Level 3: 既有逻辑 (Legacy Logic) - 现有代码**
   - 核心：作为现状参考，但必须服从 L0-L2 的修改指令。

### 8.2 脚本冲突裁决 (Inter-script Arbitration)
- **调用者优先 (Caller > Callee)**：主控脚本的需求高于模块内部实现。
- **下游优先 (Downstream > Upstream)**：以数据流末端的格式需求反向要求上游适配。
- **通用优先 (Global Utils > Local Logic)**：严禁为单一业务破坏通用工具类的稳定性。
- **风险最小化 (Minimal Disruption)**：优先选择改动成本最低、影响范围最小的方案。

### 8.3 冲突处理协议 (Conflict Protocol)
若无法自动裁决，Agent 必须：
- **识别 (Identify)**：清晰指出具体的冲突点。
- **挂起 (Suspend)**：立即停止任何写操作（进入 Read-only 模式）。
- **报告 (Report)**：提交冲突详情并给出建议方案。
- **待命 (Wait)**：等待用户显式授权后方可继续。
