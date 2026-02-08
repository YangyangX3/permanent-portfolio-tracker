# 项目说明（架构与数据约定）

**项目名**：PermanentPortfolioApp（永久投资组合追踪网页）  
**更新时间**：2026-02-08  
**目的**：记录当前版本的架构、核心功能与数据约定，便于维护与回归。

---

## 1. 产品目标与约束

### 目标
- 管理永久投资组合（四类资产桶，各 25%）
- 支持中国可购买的 ETF/股票（展示价格与涨跌幅）
- 支持现金资产（手动金额，不抓行情）
- 支持链上资产（EVM：读取钱包原生币/ERC20 余额 + CoinGecko 价格/24h 涨跌幅）
- 根据桶权重阈值（默认 15%~35%）判断是否需要再平衡
- 邮件提醒：
  - 每月第一个工作日：固定提醒检查
  - 触发再平衡阈值：发送提醒（带冷却，避免重复）

### 约束
- 默认“访问一次页面抓一次行情”，不做前端轮询
- 不做自动交易/自动下单
- 数据源为公开接口（非官方），需容错

---

## 2. 数据文件（`PermanentPortfolioApp/data/`）

### `portfolio.json`
单用户持仓与配置，核心字段：
- `categories[]`：四类桶（`equity/cash/gold/bond`），每个桶有 `target_weight/min_weight/max_weight`
- `assets[]`：资产列表
  - `id`：资产唯一 ID
  - `kind`：`cn | crypto | cash`
  - `category_id`：所属桶（可空=未分配）
  - `bucket_weight`：桶内占比（可空；用于资金分配建议拆分到具体资产）
  - `cn`：`code/name/quantity`
  - `cash`：`cash_amount_cny`
  - `crypto`：`chain/wallet/token_address/coingecko_id`（钱包余额只读）

### `notifications.json`
邮件防重复状态：
- `monthly_last_sent_yyyymm`
- `threshold_last_sent_epoch`
- `threshold_last_hash`（基于**再平衡阈值提醒**内容生成）

### `app_settings.json`
网页内设置覆盖项：
- 邮件开关、收件人、发件人、时区、定时任务时间、冷却时间
- SMTP 配置（host/port/username/starttls）
- `smtp_password_enc`：SMTP 密码的加密密文（Fernet）

### `secret.key`
SMTP 密码加密密钥（本地生成）。没有该文件将无法解密历史保存的 SMTP 密码。

---

## 3. 页面与路由（Web UI）

### 页面（Next.js）
- `/`：概览页（组合市值、再平衡提醒、四类资产桶、资金分配建议等）
- `/assets`：资产管理（拖拽分桶、增删改、批量保存）
- `/ledger`：记账（本金投入/取出、收益与年化）
- `/settings`：设置（邮件/时区/定时/冷却/链上滑点、测试邮件）

### 关键接口（JSON API）
- `GET /api/v2/state`
- 资产：`POST /api/v2/assets`、`POST /api/v2/assets/{id}/move`、`POST /api/v2/assets/batch`、`DELETE /api/v2/assets/{id}`
- 记账：`GET /api/v2/ledger/metrics`、`GET /api/ui/ledger-days`、`POST /api/v2/ledger`、`DELETE /api/v2/ledger/{id}`
- 设置：`GET /api/v2/settings`、`POST /api/v2/settings`、`POST /api/v2/settings/test-email`

---

## 4. 行情/余额数据源

### 中国股票/ETF/LOF
- 优先：`qt.gtimg.cn`（腾讯行情字符串）
- 解析：`app/quotes.py`

### 场外基金（兜底）
- `fundgz.1234567.com.cn`（估值；部分代码会返回空）
- fallback：`api.fund.eastmoney.com/f10/lsjz`（最新净值/日涨幅）

### 链上资产（EVM）
- 余额：通过 `PP_RPC_{链名大写}` 指定的 JSON-RPC 调用（`eth_getBalance` / `eth_call`）
- 价格：CoinGecko `/coins/markets?vs_currency=cny&ids=...`

---

## 5. 再平衡与提醒规则

- 再平衡判定以“**四类资产桶权重**”为准（不是单资产）
- 默认阈值：每桶 15%~35%，目标 25%
- 邮件触发：
  - 月初第一个工作日：发送月度提醒（只发一次/每月）
  - 若 `rebalance_warnings` 非空：发送阈值提醒（受冷却与 hash 去重约束）

---

## 6. 已知限制（当前版本）

- “新增资金自动分配”目前为建议/清单，不会自动下单
- 链上资产来自钱包余额（只读），不应被“应用资金”直接修改
- 公开行情源可能与支付宝/券商口径不一致

---

## 7. 测试基线

`python -m pytest -q` 应通过；覆盖：
- 腾讯行情解析与代码映射
- 再平衡桶阈值触发
- 新增资金建议的金额守恒与桶内占比拆分
- SMTP 密码加密解密 roundtrip
