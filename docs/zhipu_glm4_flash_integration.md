# 智谱AI GLM-4-Flash 免费模型集成文档

## 一、概述

GLM-4-Flash 是智谱AI提供的免费大语言模型API，可用于翻译、对话、文本生成等任务。本文档记录API调用方式及测试结果。

## 二、模型信息

| 项目 | 内容 |
|------|------|
| API端点 | `https://open.bigmodel.cn/api/paas/v4/chat/completions` |
| 免费模型 | `glm-4-flash`、`glm-4-flashx`、`glm-4-flash-250414` |
| 官方SDK | `pip install zhipuai` |
| 官方文档 | https://open.bigmodel.cn/dev/api |
| 控制台 | https://open.bigmodel.cn/ |

## 三、调用方式

### 方式一：官方SDK（推荐）

```python
from zhipuai import ZhipuAI

client = ZhipuAI(api_key="你的API_KEY")

response = client.chat.completions.create(
    model="glm-4-flash",
    messages=[
        {"role": "system", "content": "你是一个专业的翻译助手"},
        {"role": "user", "content": "需要翻译的文本"}
    ]
)
print(response.choices[0].message.content)
```

### 方式二：HTTP请求

```python
import requests

API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
API_KEY = "你的API_KEY"

headers = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

payload = {
    "model": "glm-4-flash",
    "messages": [
        {"role": "user", "content": "你好"}
    ],
    "temperature": 0.7,
    "max_tokens": 1000
}

response = requests.post(API_URL, headers=headers, json=payload, timeout=30)
result = response.json()
content = result["choices"][0]["message"]["content"]
```

### 方式三：流式输出

```python
payload = {
    "model": "glm-4-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": True
}

response = requests.post(API_URL, headers=headers, json=payload, stream=True)
for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: ') and line[6:] != '[DONE]':
            chunk = json.loads(line[6:])
            content = chunk["choices"][0]["delta"].get("content", "")
            print(content, end="")
```

## 四、核心参数说明

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| model | String | 是 | 模型名称，如 `glm-4-flash` |
| messages | List | 是 | 对话消息列表 |
| temperature | Float | 否 | 随机性控制，范围0.0-1.0，默认0.75 |
| max_tokens | Integer | 否 | 最大输出token数 |
| stream | Boolean | 否 | 是否流式输出，默认False |
| top_p | Float | 否 | 核采样参数，默认0.9 |

### messages格式

```python
messages = [
    {"role": "system", "content": "系统提示词"},  # 可选，设定角色
    {"role": "user", "content": "用户输入"},      # 必需
    {"role": "assistant", "content": "助手回复"}  # 多轮对话时使用
]
```

## 五、测试结果

### 测试环境
- 系统：Windows 11
- Python：3.13.0
- 测试时间：2026-02-26

### 测试一：基础对话

```
请求: "你好，请用一句话介绍你自己。"
响应: "我是一个致力于提供丰富知识和解答问题的AI助手。"
状态: ✅ 成功
Token消耗: 输入13 + 输出12 = 25
```

### 测试二：流式输出

```
请求: "请用三句话介绍Python编程语言。"
响应: "Python是一种高级编程语言，以其简洁明了的语法和强大的库支持而闻名；它广泛应用于网站开发、数据分析、人工智能等多个领域；Python拥有庞大的社区支持，易于学习和使用。"
状态: ✅ 成功
```

### 测试三：翻译任务

```
请求: "The quick brown fox jumps over the lazy dog."
响应: "这只快速棕色的狐狸跳过那只懒惰的狗。"
状态: ✅ 成功
```

## 六、翻译任务最佳实践

### System Prompt配置

```python
messages = [
    {
        "role": "system", 
        "content": "你是一个专业的翻译助手，将英文翻译成中文，保持准确流畅，不要添加额外解释。"
    },
    {"role": "user", "content": english_text}
]
```

### 批量翻译建议

```python
def batch_translate(texts: list[str], api_key: str) -> list[str]:
    results = []
    client = ZhipuAI(api_key=api_key)
    
    for text in texts:
        response = client.chat.completions.create(
            model="glm-4-flash",
            messages=[
                {"role": "system", "content": "翻译成中文，只返回翻译结果"},
                {"role": "user", "content": text}
            ],
            temperature=0.3
        )
        results.append(response.choices[0].message.content)
    
    return results
```

## 七、与现有翻译服务对比

| 对比项 | GLM-4-Flash | Google Translate API |
|--------|-------------|---------------------|
| 费用 | 免费 | 付费 |
| 质量 | 优秀 | 良好 |
| 速度 | 快 | 快 |
| 上下文理解 | 支持 | 不支持 |
| 专业术语 | 较好 | 一般 |

## 八、注意事项

1. **API Key安全**：不要将API Key提交到代码仓库，使用环境变量管理
2. **请求超时**：建议设置30秒以上超时时间
3. **错误处理**：需要处理网络异常、API限流等情况
4. **温度参数**：翻译任务建议使用较低的temperature（0.3-0.5）以获得更稳定输出

## 九、集成建议

### 环境变量配置

```env
ZHIPU_API_KEY=你的API_KEY
```

### 服务封装示例

```python
import os
from zhipuai import ZhipuAI

class ZhipuTranslator:
    def __init__(self):
        self.client = ZhipuAI(api_key=os.environ.get("ZHIPU_API_KEY"))
        self.model = "glm-4-flash"
    
    def translate(self, text: str, target_lang: str = "中文") -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": f"翻译成{target_lang}，只返回翻译结果"},
                {"role": "user", "content": text}
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
```

## 十、参考链接

- 智谱AI开放平台：https://open.bigmodel.cn/
- API文档：https://open.bigmodel.cn/dev/api
- SDK GitHub：https://github.com/MetaGLM/zhipuai-sdk-python-v4
