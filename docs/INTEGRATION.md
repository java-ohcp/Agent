# 感知与决策模块接口约定

已对应 `java-ohcp/backend` 增强分支的 `POST /api/v1/knowledge/search`。
两边 PR 均合并后可直接联调；旧后端尚无该端点时需要先升级。

## 检索请求

配置完整 URL `KNOWLEDGE_SEARCH_URL`，使用 POST，Content-Type 为 application/json。
可通过 `KNOWLEDGE_SEARCH_TOKEN` 提供 Bearer Token。

```json
{
  "crop": "水稻",
  "query": "作物：水稻\n症状：老叶均匀黄化，分蘖减少\n生育期：分蘖期",
  "topK": 8
}
```

## 检索响应

成功返回 HTTP 200。支持后端统一包装 `{ "code": 0, "data": { "matches": [...] } }`，
并兼容以下裸响应。零命中是空 matches；非零业务 code 作为检索故障处理，不冒充零命中。

```json
{
  "matches": [
    {
      "id": "knowledge-record-id",
      "nutrient": "氮",
      "crops": ["水稻"],
      "text": "此处由后端填入实际采集、审核的症状诊断证据",
      "sourceUrl": "https://example.org/replace-with-real-source",
      "score": 0.85
    }
  ]
}
```

示例内容仅展示字段，不作为生产知识或真实爬取结果。每条证据需要唯一 ID、元素名称、
适用作物列表、正文、来源及 `[0,1]` 的相似度；通用证据使用 `crops: ["通用"]`。
不适用作物、缺失字段、非法分数的记录会被过滤；重复 ID 保留最高分记录。
`nutrient` 应为单个规范元素名称，不应包含多个元素或整段建议。

## 传递给施肥建议模块

`Decision.candidates` 提供 nutrient、matchScore、evidenceIds；`Decision.evidence`
只在 READY 时包含被选择的引用证据。后续建议模块应自行检索对应施肥知识，保留来源，
对剂量适用的作物、地域、生育期、单位及土壤条件逐一校验。

NEED_MORE_INFO 的 evidence 用于上游排查检索情况，不应据此触发施肥建议。
调用方务必先检查 status，READY 表示可移交候选结果，不能解释成确诊。

推荐 URL 为 `http://127.0.0.1:8080/api/v1/knowledge/search`，端口按实际部署修改。
后端 score 是规则与检索综合的归一化启发式分数，阈值仍需用评测数据校准。
HTTP 客户端接收超过 1 MiB 时取消订阅，拒绝多余尾随 JSON；来源仅接受不含用户凭据的 HTTP(S) 地址。
真实模型、鉴权方式和部署配置仍由宿主提供，测试不代替真实模型联调。
