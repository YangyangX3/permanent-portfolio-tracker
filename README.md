# Permanent Portfolio Tracker

一个自托管的永久组合（Permanent Portfolio）投资追踪工具，支持实时行情、再平衡提醒、资金分配建议与收益计算。

> **安全提示**：项目默认**无登录鉴权**，请仅在本机或受信任内网使用。如需公网访问，务必配合反向代理鉴权（如 Nginx BasicAuth、Cloudflare Tunnel）。

---

## 什么是永久组合

永久组合（Permanent Portfolio）由 Harry Browne 提出，将资产平均分配到四类：

| 类别 | 目标权重 | 作用                |
| ---- | -------- | ------------------- |
| 股票 | 25%      | 经济增长期获利      |
| 债券 | 25%      | 经济繁荣期获利      |
| 黄金 | 25%      | 通胀时期保值        |
| 现金 | 25%      | 经济衰退/通缩期防御 |

当一个类别的权重偏离设定区间（默认 15%–35%）时，工具会提醒你进行再平衡。

---

## 功能特性

- **多源行情**：A股/ETF/基金（腾讯财经、天天基金）、加密货币（CoinGecko）、链上余额（EVM + Solana）
- **再平衡检测**：四类资产偏离阈值时触发提醒
- **资金分配**：输入新增资金，自动计算各类别/资产的买入金额
- **收益追踪**：记录出入金流水，计算本金、盈亏及 XIRR 年化收益率
- **历史趋势**：定期快照组合状态，前端展示 Sparkline 走势图
- **邮件通知**：月初提醒 + 阈值告警（可配置 SMTP）
- **拖拽分类**：前端支持拖拽将资产归类到不同大类
- **深色模式**：支持亮色/深色主题切换

---

## 技术栈

| 层       | 技术                                              |
| -------- | ------------------------------------------------- |
| 后端     | Python 3.11 · FastAPI · Uvicorn · APScheduler     |
| 前端     | Next.js 15 · React 19 · TypeScript · Tailwind CSS |
| 数据存储 | 本地 JSON 文件（无需数据库）                      |
| 部署     | Docker Compose                                    |

---

## 快速开始

### 方式A：Docker Compose（推荐）

适合 VPS、NAS 或家用服务器。

```bash
# 1. 克隆仓库
git clone https://github.com/YangyangX3/PermanentPortfolioApp.git
cd PermanentPortfolioApp

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env：设置端口、时区、SMTP、RPC 端点等

# 3. 启动
docker compose up -d --build

# 4. 访问 http://localhost:8010
```

### 方式B：本地开发

**后端：**

```bash
python -m venv .venv
.\.venv\Scripts\Activate.ps1  # Windows (PowerShell)
pip install -r requirements.txt
python -m uvicorn app.main:app --port 8010
```

**前端：**

```bash
cd web
cp .env.local.example .env.local
npm install
npm run dev
```

访问 http://127.0.0.1:3000

---

## 项目结构

```
├── app/                  # FastAPI 后端
│   ├── main.py           # API 路由入口
│   ├── portfolio.py      # 组合数据模型
│   ├── quotes.py         # 多源行情获取与缓存
│   ├── chain.py          # 链上余额查询（EVM + Solana）
│   ├── rebalance.py      # 再平衡检测与视图计算
│   ├── rebalance_suggest.py  # 加仓分配算法
│   ├── ledger.py         # 出入金流水与 XIRR 计算
│   ├── snapshots.py      # 历史快照（时间序列）
│   ├── scheduler.py      # 定时任务调度
│   ├── settings.py       # 配置管理
│   └── mailer.py         # 邮件发送
├── web/                  # Next.js 前端
│   └── src/
│       ├── app/          # 页面（概览/资产/流水/设置）
│       └── components/   # UI 组件
├── data/                 # 持久化数据（JSON 文件，被 .gitignore 忽略）
│   ├── portfolio.json    # 持仓配置
│   ├── ledger.json       # 记账数据
│   ├── snapshots.jsonl   # 历史快照
│   └── secret.key        # 加密密钥（请备份）
├── tests/                # 测试用例
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

---

## 使用指南

| 路径        | 功能说明                                 |
| ----------- | ---------------------------------------- |
| `/`         | 概览：组合市值、再平衡状态、资金分配建议 |
| `/assets`   | 资产管理：增删改、拖拽分桶、批量保存     |
| `/ledger`   | 记账：本金投入/取出、收益与 XIRR         |
| `/settings` | 设置：邮件/时区/定时/链上滑点、测试邮件  |

### 数据文件说明

所有配置和账本存储在 `data/` 目录（默认被 `.gitignore` 忽略，不会提交到 Git）：

- `portfolio.json` - 持仓与资产桶配置
- `ledger.json` - 记账数据
- `notifications.json` - 邮件防重复状态
- `snapshots.jsonl` - 历史快照
- `app_settings.json` - 网页设置覆盖
- `secret.key` - SMTP 密码加密密钥

> **建议：定期备份整个 `data/` 文件夹。**

---

## 环境变量

| 变量                               | 默认值                                | 必填 | 说明                         |
| ---------------------------------- | ------------------------------------- | ---- | ---------------------------- |
| `PP_PORT`                          | `8010`                                | 否   | 前端对外暴露端口             |
| `PP_TIMEZONE`                      | `Asia/Shanghai`                       | 否   | 时区                         |
| `PP_EMAIL_ENABLED`                 | `false`                               | 否   | 是否启用邮件通知             |
| `PP_DAILY_JOB_TIME`                | `09:05`                               | 否   | 每日定时任务执行时间         |
| `PP_NOTIFY_COOLDOWN_MINUTES`       | `360`                                 | 否   | 阈值告警邮件冷却时间（分钟） |
| `PP_CRYPTO_SLIP_PCT`               | `1`                                   | 否   | 加密货币滑点百分比           |
| `PP_CACHE_ACTIVE_REFRESH_SECONDS`  | `4`                                   | 否   | 活跃状态行情刷新间隔（秒）   |
| `PP_CACHE_IDLE_REFRESH_SECONDS`    | `20`                                  | 否   | 空闲状态行情刷新间隔（秒）   |
| `PP_CACHE_IDLE_AFTER_SECONDS`      | `60`                                  | 否   | 进入空闲状态判定时间（秒）   |
| `PP_CACHE_MIN_REFRESH_GAP_SECONDS` | `1`                                   | 否   | 行情刷新最小间隔（秒）       |
| `PP_SNAPSHOT_INTERVAL_SECONDS`     | `60`                                  | 否   | 快照记录间隔（秒）           |
| `PP_SMTP_HOST`                     | -                                     | 否   | SMTP 服务器地址              |
| `PP_SMTP_PORT`                     | `587`                                 | 否   | SMTP 端口                    |
| `PP_SMTP_USERNAME`                 | -                                     | 否   | SMTP 用户名                  |
| `PP_SMTP_PASSWORD`                 | -                                     | 否   | SMTP 密码（存储时加密）      |
| `PP_SMTP_USE_STARTTLS`             | `true`                                | 否   | SMTP 是否启用 STARTTLS       |
| `PP_MAIL_FROM`                     | -                                     | 否   | 发件人邮箱                   |
| `PP_MAIL_TO`                       | -                                     | 否   | 收件人邮箱（可多个）         |
| `PP_RPC_ETH`                       | -                                     | 否   | 以太坊 RPC 端点              |
| `PP_RPC_BSC`                       | -                                     | 否   | BSC RPC 端点                 |
| `PP_RPC_POLYGON`                   | -                                     | 否   | Polygon RPC 端点             |
| `PP_RPC_SOLANA`                    | `https://api.mainnet-beta.solana.com` | 否   | Solana RPC 端点              |

---

## 系统要求

- **Docker 部署**：Docker 20.10+ 与 Docker Compose 2.0+
- **本地开发**：Python 3.11+ 与 Node.js 18.18+（或 20+）

---

## 常见问题

**Q: 价格更新有多快？**
A: 项目设计初衷是长期投资组合追踪，非短线交易。默认行情缓存几毫秒到几十秒不等，可通过环境变量调整。

**Q: 支持美股吗？**
A: 当前行情源主要针对中国市场。如需美股支持，欢迎贡献 PR。

---

## 测试

**后端：**

```bash
pip install -r dev-requirements.txt
pytest -q
```

**前端：**

```bash
cd web
npm ci
npm run build
```

---

## 许可证

[MIT](LICENSE)
