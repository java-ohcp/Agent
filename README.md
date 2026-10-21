# OHCP Agent 智能体模块

本仓库按智能体四大板块逐步实现：

1. **感知输入**：作物症状、环境信息与文档文本清洗
2. **思考决策**：检索证据、校验、模型决策与补充问题
3. **行动执行**：工具调用、文件/API 操作、子任务分发
4. **记忆与反馈闭环**：短期上下文、长期记忆、状态检查点、结果回传

当前代码同时包含两个可独立集成的部分：

- `src/main/java/local/agent/crop/`：作物营养智能体的感知与决策模块（第 1、2 版块）
- `agent/`、`examples/`、`tests/`：Python 行动执行与记忆反馈示例（第 3、4 版块）

## 作物营养智能体

处理流程：

症状与环境输入 → Perception 清洗 → KnowledgeSearch 调用团队检索接口
→ 校验证据适用作物与相似度 → LangChain4j 经 Spring AI 模型生成决策
→ 校验引用 ID、候选数量与状态 → 返回候选、证据或补充问题。

没有检索证据时不调用模型。候选名称和分数均从已引用的后端证据解析，
分数是检索相似度，不是经过标定的诊断概率。模块采用固定步骤规划和一次有界重试，
不输出内部思维过程，不实现任意工具执行。

### Java 集成

需要 Java 17+、Maven。运行：

```powershell
mvn test
mvn package
```

后端已有配置中，可以使用已配置好的 Spring AI `ChatModel` 构建智能体：

```java
import local.agent.crop.*;
import java.net.URI;

var search = new HttpKnowledgeSearch(
    URI.create(System.getenv("KNOWLEDGE_SEARCH_URL")),
    System.getenv("KNOWLEDGE_SEARCH_TOKEN"));
var agent = new CropNutritionAgent(search, new SpringAiDecisionModel(chatModel), 0.5);
var result = agent.analyze(new Contracts.Input(
    "水稻", "下部老叶均匀黄化，植株矮小，分蘖减少", "分蘖期", "近期多雨", "", ""));
```

接口约定见 [docs/INTEGRATION.md](docs/INTEGRATION.md)。默认建议协议尚待真实接口样例确认；
如字段或响应包装不同，只需修改 `HttpKnowledgeSearch`，也可以直接实现 `KnowledgeSearch`。

`Input.documentText` 和 `imageSymptoms` 接收上游已提取文本，不直接解析文档或图片。
模块不保留会话；多轮补充信息由上游合并成新 `Input` 再次调用。

## Python 行动执行与反馈闭环

### 第 3 版块：行动执行

- 工具注册、调用、重试、耗时统计
- 文件读写与目录穿越防护
- HTTP JSON 请求与主机白名单
- 多智能体/Worker 子任务分发
- 工具白名单、黑名单、危险操作确认

核心文件：

- `agent/action.py`
- `agent/builtin_tools.py`

### 第 4 版块：记忆与反馈闭环

- 短期上下文：数量与字符量双重限制
- 长期记忆：JSON 持久化、TTL、关键词召回、原子保存
- 状态检查点：每一步落盘，方便中断恢复
- Think → Act → Observe → Remember 循环
- 步数上限、重复动作防死循环、安全异常

核心文件：

- `agent/memory.py`
- `agent/loop.py`

运行 Python 示例和测试：

```powershell
python examples\demo.py
python -m unittest discover -s tests -v
```

Python 侧通过 `Decision` 注入第 1、2 版块的决策结果，因此后续接入真实感知模块或 LLM
规划模块时，不需要重写行动执行和记忆闭环。

## CI 与自动合并

- `.github/workflows/ci.yml`：push / PR 时运行 Python 测试。
- `.github/workflows/auto-merge.yml`：同一仓库的 PR 添加 `automerge` 标签后，
  在分支保护和检查通过时启用 squash auto-merge。
- `.github/ruleset-protect-main.json`：可导入的 `main` 分支保护规则集。

使用自动合并前，需要在仓库 Settings → General → Pull Requests 中打开
**Allow auto-merge**。自动合并不会绕过分支保护，也不会替代代码审查。

测试使用合成证据与模拟模型，不代表农艺有效性验证，不依赖真实 API 密钥。
