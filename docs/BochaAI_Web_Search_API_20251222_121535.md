# BochaAI_Web_Search_API

> 来源: https://bocha-ai.feishu.cn/wiki/RXEOw02rFiwzGSkd9mUcqoeAnNK
> 爬取时间: 2025-12-22 12:15:35
> 方式: 浏览器提取

---

博查用户帮助文档
Web Search API

一、API简介
从全网搜索任何网页信息和网页链接，结果准确、摘要完整，更适合AI使用。
可配置搜索时间范围、是否显示摘要，支持按分页获取更多结果。

二、搜索结果
包括网页、图片、视频，Response格式兼容Bing Search API。
• 网页包括name、url、snippet、summary、siteName、siteIcon、datePublished等信息
• 图片包括 contentUrl、hostPageUrl、width、height等信息

三、API接口
请求方式: POST
请求地址: https://api.bochaai.com/v1/web-search

四、请求参数
| 参数 | 类型 | 必填 | 描述 |
| --- | --- | --- | --- |
| query | string | 是 | 搜索关键词 |
| freshness | string | 否 | 搜索时间范围（noLimit, oneDay, oneWeek, oneMonth） |
| count | integer | 否 | 返回结果数量（默认10，最大50） |
| offset | integer | 否 | 偏移量 |

五、响应定义
返回结果包含 webPages, images, videos 等模块。
每个网页包含 title, url, snippet, datePublished, siteName 等。

六、Python SDK 示例
```python
import requests
import json

url = "https://api.bochaai.com/v1/web-search"
payload = json.dumps({
  "query": "彩讯股份",
  "freshness": "oneMonth",
  "count": 10
})
headers = {
  'Authorization': 'Bearer YOUR_API_KEY',
  'Content-Type': 'application/json'
}
response = requests.request("POST", url, headers=headers, data=payload)
print(response.text)
```

