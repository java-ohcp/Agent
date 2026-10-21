# 感知与决策模块接口约定

以下为等待团队确认的默认适配协议，不是已存在后端接口的描述。

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

成功返回 HTTP 200；零命中返回 `{"matches":[]}`。

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

尚待提供：实际 URL、鉴权方式、请求/响应样例、相似度计算方式，以及宿主模型配置。
