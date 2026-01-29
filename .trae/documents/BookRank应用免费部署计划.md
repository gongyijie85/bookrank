## 部署目标
将BookRank应用免费部署到Render平台

## 部署步骤

### 第一步：准备GitHub仓库（安全推送代码）
1. 确保.gitignore正确配置（排除.env）
2. 创建GitHub仓库
3. 推送代码（不包含API密钥）

### 第二步：注册Render账号
1. 访问render.com
2. 使用GitHub账号登录
3. 授权访问仓库

### 第三步：创建PostgreSQL数据库
1. 在Render中创建免费PostgreSQL数据库
2. 记录数据库连接信息

### 第四步：部署Web服务
1. 创建Web Service
2. 配置环境变量（安全输入API密钥）
3. 部署应用

### 第五步：初始化数据库
1. 运行数据库初始化命令
2. 验证部署成功

## 安全保障
- ✅ .env文件已在.gitignore中
- ✅ 使用.env.example作为模板
- ✅ API密钥只在Render控制台输入，不写入代码
- ✅ 数据库密码由Render自动生成

## 需要的工具
- Git（已安装）
- 浏览器（用于操作GitHub和Render）

请确认这个计划后，我将一步步指导你操作。