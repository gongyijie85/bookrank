# BookRank 公开API文档

## 概述

BookRank 提供公开API，允许外部系统获取畅销书排行榜和获奖图书数据。

**基础URL**: `https://bookrank-ckml.onrender.com/api/public`

**限流策略**: 每个IP每分钟最多60次请求

## 响应格式

所有API响应均为JSON格式：

```json
{
  "success": true,
  "data": { ... },
  "message": "Success",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

错误响应：

```json
{
  "success": false,
  "message": "Error message",
  "timestamp": "2024-01-01T00:00:00Z"
}
```

---

## API端点

### 1. API信息

```
GET /api/public
```

获取API基本信息和所有可用端点。

**响应示例**:

```json
{
  "success": true,
  "data": {
    "name": "BookRank Public API",
    "version": "1.0.0",
    "description": "提供畅销书排行榜和获奖图书数据的公开API",
    "endpoints": [...],
    "rate_limit": "60 requests per minute per IP"
  }
}
```

---

### 2. 获取所有分类畅销书

```
GET /api/public/bestsellers
```

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 10 | 每个分类返回的图书数量（最大50）|

**响应示例**:

```json
{
  "success": true,
  "data": {
    "categories": {
      "hardcover-fiction": "精装小说",
      "hardcover-nonfiction": "精装非虚构",
      "trade-fiction-paperback": "平装小说",
      "paperback-nonfiction": "平装非虚构"
    },
    "books": {
      "hardcover-fiction": {
        "category_name": "精装小说",
        "books": [...]
      }
    },
    "last_updated": "2024-01-01T00:00:00Z"
  }
}
```

---

### 3. 获取指定分类畅销书

```
GET /api/public/bestsellers/{category}
```

**路径参数**:

| 参数 | 说明 |
|------|------|
| category | 分类ID: `hardcover-fiction`, `hardcover-nonfiction`, `trade-fiction-paperback`, `paperback-nonfiction` |

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| limit | int | 20 | 返回的图书数量（最大50）|

**响应示例**:

```json
{
  "success": true,
  "data": {
    "category_id": "hardcover-fiction",
    "category_name": "精装小说",
    "books": [
      {
        "id": 1,
        "title": "Book Title",
        "author": "Author Name",
        "isbn13": "9780000000000",
        "rank": 1,
        "description": "Book description...",
        "cover_url": "https://..."
      }
    ],
    "total": 15,
    "last_updated": "2024-01-01T00:00:00Z"
  }
}
```

---

### 4. 搜索畅销书

```
GET /api/public/bestsellers/search?keyword={keyword}
```

**查询参数**:

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| keyword | string | 是 | 搜索关键词（至少2个字符）|
| limit | int | 否 | 返回结果数量（默认20，最大50）|

**响应示例**:

```json
{
  "success": true,
  "data": {
    "keyword": "king",
    "books": [...],
    "total": 5
  }
}
```

---

### 5. 获取所有奖项列表

```
GET /api/public/awards
```

**响应示例**:

```json
{
  "success": true,
  "data": {
    "awards": [
      {
        "id": 1,
        "name": "普利策奖",
        "name_en": "Pulitzer Prize",
        "description": "美国新闻界最高荣誉",
        "book_count": 5
      }
    ],
    "total": 7
  }
}
```

---

### 6. 获取指定奖项的获奖图书

```
GET /api/public/awards/{award_name}
```

**路径参数**:

| 参数 | 说明 |
|------|------|
| award_name | 奖项名称（如：普利策奖、布克奖、雨果奖等）|

**查询参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| year | int | 无 | 筛选年份 |
| limit | int | 20 | 返回数量（最大50）|

**响应示例**:

```json
{
  "success": true,
  "data": {
    "award": {
      "id": 1,
      "name": "普利策奖",
      "name_en": "Pulitzer Prize",
      "description": "..."
    },
    "books": [...],
    "total": 5,
    "years": [2025, 2024, 2023, 2022]
  }
}
```

---

### 7. 获取指定奖项和年份的获奖图书

```
GET /api/public/awards/{award_name}/{year}
```

**路径参数**:

| 参数 | 说明 |
|------|------|
| award_name | 奖项名称 |
| year | 年份 |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "award": {
      "id": 1,
      "name": "普利策奖",
      "name_en": "Pulitzer Prize"
    },
    "year": 2024,
    "books": [...],
    "total": 1
  }
}
```

---

### 8. 获取图书详细信息

```
GET /api/public/book/{isbn}
```

**路径参数**:

| 参数 | 说明 |
|------|------|
| isbn | 图书ISBN-13 |

**响应示例**:

```json
{
  "success": true,
  "data": {
    "book": {
      "id": 1,
      "title": "Book Title",
      "author": "Author Name",
      "isbn13": "9780000000000",
      "description": "...",
      "cover_url": "https://..."
    },
    "source": "bestseller"
  }
}
```

---

## 可用奖项列表

| 奖项名称 | 英文名称 |
|---------|---------|
| 普利策奖 | Pulitzer Prize |
| 布克奖 | Booker Prize |
| 诺贝尔文学奖 | Nobel Prize in Literature |
| 雨果奖 | Hugo Award |
| 美国国家图书奖 | National Book Award |
| 星云奖 | Nebula Award |
| 国际布克奖 | International Booker Prize |
| 爱伦·坡奖 | Edgar Award |

---

## 错误代码

| HTTP状态码 | 说明 |
|-----------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 404 | 资源未找到 |
| 429 | 请求过于频繁（限流）|
| 500 | 服务器内部错误 |

---

## 使用示例

### JavaScript (fetch)

```javascript
// 获取精装小说畅销书
fetch('https://bookrank-ckml.onrender.com/api/public/bestsellers/hardcover-fiction?limit=10')
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log('Books:', data.data.books);
    }
  });
```

### Python (requests)

```python
import requests

# 获取普利策奖2024年获奖图书
response = requests.get(
    'https://bookrank-ckml.onrender.com/api/public/awards/普利策奖/2024'
)
data = response.json()

if data['success']:
    for book in data['data']['books']:
        print(f"{book['title']} by {book['author']}")
```

### cURL

```bash
# 搜索图书
curl "https://bookrank-ckml.onrender.com/api/public/bestsellers/search?keyword=king"
```

---

## 注意事项

1. **限流**: 每个IP每分钟最多60次请求，超过限制将返回429错误
2. **数据更新**: 畅销书数据每周更新一次，获奖图书数据根据奖项公布时间更新
3. **图片链接**: 封面图片URL可能来自Open Library或Google Books，请处理图片加载失败的情况
4. **编码**: 所有API响应使用UTF-8编码

---

## 联系方式

如有问题或建议，请访问：https://github.com/gongyijie85/bookrank
