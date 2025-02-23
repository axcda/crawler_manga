# Crawel-GMH

一个高性能的分布式网络爬虫系统，支持自动化数据采集、处理和存储。

## 项目描述

Crawel-GMH 是一个基于 Python 的现代化网络爬虫框架，具有以下特点：
- 分布式架构设计，支持横向扩展
- 内置反爬虫策略，包括 Cloudflare Turnstile 验证码处理
- 支持异步并发爬取，提高效率
- 模块化设计，易于扩展和维护
- 完善的日志记录和监控系统

## 技术栈

- **核心框架：** 
  - FastAPI（API服务）
  - Scrapy（爬虫框架）
  - Selenium（浏览器自动化）
- **网络请求：** 
  - requests
  - aiohttp（异步请求）
  - httpx（现代HTTP客户端）
- **数据解析：** 
  - BeautifulSoup4
  - lxml
  - xpath
  - re（正则表达式）
- **数据存储：** 
  - MongoDB（非结构化数据）
    - [✅] 漫画详细信息集合
    - [✅] 章节内容集合
    - [ ] 用户设置集合
    - [ ] 系统配置集合
  - Redis（缓存和队列）
    - [ ] 热门漫画缓存
    - [ ] 用户会话管理
    - [ ] 访问频率限制
    - [ ] 任务队列
    - [ ] 实时计数器
- **并发处理：** 
  - asyncio（异步IO）
  - multiprocessing（多进程）
  - threading（多线程）
- **反爬虫对策：** 
  - User-Agent池
  - IP代理池
  - 请求延迟控制
  - Cloudflare Turnstile 处理
- **监控和日志：** 
  - Prometheus（监控指标）
  - ELK Stack（日志分析）
  - Grafana（可视化）

## 主要功能

- **数据采集**
  - 支持多种网站结构的数据爬取
  - 自动处理反爬验证
  - 智能限速和并发控制
  
- **数据处理**
  - 自动化数据清洗
  - 结构化数据提取
  - 数据验证和转换
  
- **系统特性**
  - 分布式任务调度
  - 失败重试机制
  - 实时监控告警
  - 数据导出功能

## 项目结构

```
crawel-gmh/
├── config/                 # 配置文件目录
├── data/                   # 数据存储目录
├── extractors/             # 数据提取器
├── logs/                   # 日志文件
├── models/                 # 数据模型
├── utils/                  # 工具函数
├── Turnstile-Solver/       # Cloudflare验证码处理
├── backup/                 # 备份文件
├── fastapi_server.py      # FastAPI服务器
├── server_control.py      # 服务器控制脚本
├── test_api.py            # API测试
├── requirements.txt       # 项目依赖
├── Dockerfile             # Docker构建文件
├── docker-compose.yml     # Docker编排配置
└── README.md              # 项目文档
```

## 快速开始

### 本地开发环境搭建

1. 克隆项目：
```bash
git clone https://github.com/yourusername/crawel-gmh.git
cd crawel-gmh
```

2. 创建并激活虚拟环境：
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows
```

3. 安装依赖：
```bash
pip install -r requirements.txt
```

4. 配置环境：
```bash
cp config/config.example.yml config/config.yml
# 编辑 config.yml 设置你的配置
```

5. 运行测试：
```bash
pytest test_api.py
```

### Docker 部署

1. 构建镜像：
```bash
docker build -t crawel-gmh .
```

2. 使用 docker-compose 运行：
```bash
docker-compose up -d
```

### 配置说明

#### 环境变量配置

| 环境变量 | 说明 | 默认值 | 示例 |
|---------|------|--------|------|
| MONGODB_URI | MongoDB连接URI | mongodb://localhost:27017 | mongodb://user:pass@host:27017/db |
| MYSQL_URI | MySQL连接URI | mysql://localhost:3306/db | mysql://user:pass@host:3306/db |
| REDIS_URI | Redis连接URI | redis://localhost:6379 | redis://user:pass@host:6379/0 |
| LOG_LEVEL | 日志级别 | INFO | DEBUG/INFO/WARNING/ERROR |
| MAX_WORKERS | 最大工作进程数 | 4 | 8 |
| REQUEST_TIMEOUT | 请求超时时间(秒) | 30 | 60 |
| PROXY_ENABLED | 是否启用代理 | false | true |

#### 数据卷说明

- `/app/data`: 数据存储目录
- `/app/logs`: 日志文件目录
- `/app/config`: 配置文件目录
- `/app/backup`: 备份文件目录

## API 文档

启动服务后访问 `http://localhost:7056/docs` 查看完整的 API 文档。

### 漫画接口

| 接口 | 方法 | 说明 | 示例 |
|-----|------|------|------|
| `/api/manga/home` | GET | 获取漫画首页信息 | `http://localhost:7056/api/manga/home` |
| `/api/manga/search/{keyword}` | GET | 搜索漫画 | `http://localhost:7056/api/manga/search/独自` |
| `/api/manga/chapter/{manga_id}` | GET | 获取漫画章节列表 | `http://localhost:7056/api/manga/chapter/yishijieluyingliaoyushenghuo` |
| `/api/manga/content/{manga_id}/{chapter_id}` | GET | 获取漫画章节内容 | `http://localhost:7056/api/manga/content/yishijieluyingliaoyushenghuo/32382-051674750-31` |

### 接口说明

#### 1. 漫画首页
- 请求：`GET /api/manga/home`
- 响应：返回首页推荐漫画列表

#### 2. 漫画搜索
- 请求：`GET /api/manga/search/{keyword}`
- 参数：
  - `keyword`: 搜索关键词
- 响应：返回匹配的漫画列表

#### 3. 漫画章节列表
- 请求：`GET /api/manga/chapter/{manga_id}`
- 参数：
  - `manga_id`: 漫画ID
- 响应：返回漫画的所有章节信息

#### 4. 漫画内容
- 请求：`GET /api/manga/content/{manga_id}/{chapter_id}`
- 参数：
  - `manga_id`: 漫画ID
  - `chapter_id`: 章节ID
- 响应：返回章节的漫画内容

### 使用示例

```python
import requests

# 获取首页数据
response = requests.get('http://localhost:7056/api/manga/home')
home_data = response.json()

# 搜索漫画
keyword = '独自'
response = requests.get(f'http://localhost:7056/api/manga/search/{keyword}')
search_results = response.json()

# 获取章节列表
manga_id = 'yishijieluyingliaoyushenghuo'
response = requests.get(f'http://localhost:7056/api/manga/chapter/{manga_id}')
chapters = response.json()

# 获取章节内容
chapter_id = '32382-051674750-31'
response = requests.get(f'http://localhost:7056/api/manga/content/{manga_id}/{chapter_id}')
content = response.json()
```

## 开发指南

### 添加新的爬虫

1. 在 `extractors` 目录下创建新的提取器
2. 实现必要的接口方法
3. 在配置文件中注册新的爬虫

### 单元测试

```bash
pytest tests/ -v
```

## 常见问题

1. **Q: 如何处理验证码？**
   A: 系统集成了 Turnstile-Solver 用于处理 Cloudflare 验证码，其他类型验证码可通过插件扩展。

2. **Q: 如何控制爬取速度？**
   A: 在配置文件中设置 `CRAWL_DELAY` 和 `MAX_CONCURRENT_REQUESTS`。


## 许可证

[MIT License](LICENSE)

## 致谢

- [Turnstile-Solver](https://github.com/Theyka/Turnstile-Solver/) - Cloudflare Turnstile 验证码处理方案
- 所有项目贡献者

## 更新日志

### v1.0.0 (2024-02-23)
- 初始版本发布
- 支持基础爬虫功能
- 添加 Docker 部署支持