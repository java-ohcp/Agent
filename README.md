# OHCP 作物营养智能体模块

本模块负责截图中的两个部分：**感知输入**与**思考决策**。
不包含后端服务、爬虫、前端或施肥建议生成模块。
业务代码位于 local.agent.crop，可作为独立 JAR 交给后端同学集成。

## 处理流程

症状与环境输入 → Perception 清洗 → KnowledgeSearch 调用团队检索接口
→ 校验证据适用作物与相似度 → LangChain4j 经 Spring AI 模型生成决策
→ 校验引用 ID、候选数量与状态 → 返回候选、证据或补充问题。

没有检索证据时不调用模型。候选名称和分数均从已引用的后端证据解析，
分数是检索相似度，不是经过标定的诊断概率。采用固定步骤规划和一次有界重试，
不输出内部思维过程，不实现任意工具执行。后续模块负责施肥建议。

## 集成

Java 17+、Maven。运行 mvn test 测试、mvn package 构建 JAR，供后端项目引用。
依赖固定为 Spring AI 1.0.0、LangChain4j 0.36.2；团队如已确定其他版本需统一后联调。
模块不创建 Spring Boot 应用、不占用端口、不绑定模型厂商。

在后端已有配置中，使用已配置好的 Spring AI ChatModel 构建智能体：

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

0.5 仅为初始阈值，需基于你们检索器评分与评测数据校准。接口必须提供 [0,1]
归一化相似度，不能直接混用距离值。模型连接超时、请求超时、采样参数由宿主
ChatModel 配置，推荐低温度。检索端有连接/请求超时，不自动跟随重定向。
响应字符串长度检查在接收后进行，宿主还需在网络层限制响应大小与并发。

## 对接边界

默认建议协议见 [接口约定](docs/INTEGRATION.md)，尚待你们提供真实接口样例。
如字段或响应包装不同，只需修改 HttpKnowledgeSearch。
也可直接实现 KnowledgeSearch 调用已有检索服务，避免后端内部 HTTP 往返。

Input.documentText 和 imageSymptoms 接收上游已提取文本，不直接解析文档或图片。
模块不保留会话；多轮补充信息由上游合并成新 Input 再次调用。

| 状态 | 后续处理 |
|---|---|
| READY | 将候选和引用证据交给施肥建议模块，结合田间检测复核 |
| NEED_MORE_INFO | 展示 questions，补充信息后重新检索 |
| KNOWLEDGE_UNAVAILABLE | 检索服务故障，稍后重试 |

测试使用合成证据与模拟模型，不代表农艺有效性验证，不依赖真实 API 密钥。
当前尚未关联 GitHub，实际服务和模型联调需要团队提供连接配置。
