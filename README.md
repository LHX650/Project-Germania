# Project Germania

德国汽车市场价格与销量智能监测平台。

Project Germania 目标是逐步建立一套面向德国汽车市场的数据采集、清洗、存储、分析、预测和可视化系统。本仓库当前处于第一阶段：基础工程骨架。

## 当前阶段

本阶段只包含：

- 标准项目目录；
- Python `src` 布局；
- `pyproject.toml` 依赖和工具配置；
- 基础日志配置；
- 最小健康检查模块；
- pytest、ruff、black 配置；
- 健康检查测试。

本阶段不包含：

- 德国汽车市场真实数据；
- 数据库模型或迁移；
- 爬虫或 Playwright 自动化；
- Streamlit Dashboard；
- 对真实网站的连接。

## 环境要求

- Python 3.12 或更高版本；
- pip。

检查 Python 版本：

```powershell
python --version
```

## 安装

建议先创建虚拟环境：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

安装项目和开发依赖：

```powershell
pip install -e ".[dev]"
```

## 运行健康检查

```powershell
python -c "from germania.health import get_health_status; print(get_health_status())"
```

预期返回本地包状态，例如：

```text
HealthStatus(service='project-germania', status='ok', version='0.1.0')
```

## 测试和代码检查

```powershell
pytest
ruff check .
black --check .
```

## 环境变量

复制 `.env.example` 为本地 `.env` 后再填写本机配置：

```powershell
Copy-Item .env.example .env
```

`.env` 已被 `.gitignore` 忽略，不应提交真实密码、密钥、数据库地址或本地路径。

## 目录结构

```text
project-germania/
├── AGENTS.md
├── README.md
├── pyproject.toml
├── .env.example
├── .gitignore
├── config/
├── data/
│   ├── raw/
│   ├── interim/
│   ├── processed/
│   └── exports/
├── database/
├── docs/
├── logs/
├── notebooks/
├── scripts/
├── src/
│   └── germania/
│       ├── collectors/
│       ├── cleaning/
│       ├── database/
│       ├── analytics/
│       ├── forecasting/
│       ├── dashboard/
│       ├── quality/
│       └── utils/
└── tests/
    ├── fixtures/
    ├── unit/
    └── integration/
```

## 数据原则

本项目不得伪造 KBA 数据、网页抓取结果或测试结果。挂牌价不是成交价，新车注册量才是本项目中“销量”指标的优先权威口径。真实数据采集、数据库设计和 Dashboard 将在后续阶段按项目规范逐步建设。
