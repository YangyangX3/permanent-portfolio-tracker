# Product Requirements Document: 永久投资组合追踪与再平衡提醒（Web）

**Version**: 0.2 (Draft)
**Date**: 2026-01-25
**Author**: Sarah (Product Owner)
**Quality Score**: 89/100

---

## Executive Summary

本功能提供一个本地运行的网页，用于管理“永久投资组合”（如 4 类资产均衡配置）并在用户访问页面时抓取一次中国市场标的的最新价格与涨跌幅，计算当前持仓权重与目标权重偏离，触发再平衡提醒。

核心价值在于：把“资产配置—行情—偏离—提醒”整合在一个轻量工具里，减少手工核算，提高再平衡的可执行性。

补充：支持把资产拖动分配到四类资产桶（目标各 25%），并支持链上资产（EVM 钱包余额 + CoinGecko 价格/24h 涨跌幅）纳入组合计算。

---

## Problem Statement

**Current Situation**:
- 用户在不同券商/基金 App 分散持仓，难以统一看到组合权重与偏离
- 再平衡触发多依赖人工“感觉”，缺乏明确阈值与提示
- 中国标的类型多样（A 股/ETF/场外基金），数据口径不一致

**Proposed Solution**:
- 提供资产管理页面：资产名称、代码、持仓数量、目标占比、再平衡阈值
- 首页概览：访问即抓取一次行情（价格、涨跌幅），计算市值与权重
- 当权重超出阈值区间时输出醒目的提醒

**Business Impact**:
- 降低用户维护组合的时间成本
- 提升再平衡纪律性，减少“配置漂移”长期积累

---

## Success Metrics

**Primary KPIs:**
- 页面打开到数据渲染时间：P95 < 2.5s（在普通网络条件下）
- 行情成功率：> 98%（代码有效且数据源可用）
- 再平衡提醒可用性：提醒规则可解释、可复现（同一输入必然得到同一输出）

**Validation**:
- 本地日志统计请求耗时与失败率
- 使用固定样例数据进行单元测试验证权重与阈值触发逻辑

---

## User Personas

### Primary: 自主管理型长期投资者
- **Role**: 个人投资者（偏长期/配置型）
- **Goals**: 稳定持有、定期再平衡、控制单一资产偏离风险
- **Pain Points**: 手工算权重麻烦；不确定何时该再平衡；数据分散
- **Technical Level**: 中等（可本地跑脚本/网页）

---

## User Stories & Acceptance Criteria

### Story 1: 配置资产与代码

**As a** 投资者
**I want to** 在网页中新增/编辑/删除资产，并填写代码与持仓数量
**So that** 系统能按我的真实组合进行追踪与提醒

**Acceptance Criteria:**
- [ ] 支持新增资产：代码、名称（可空）、持仓数量、目标占比、最小/最大阈值
- [ ] 支持编辑并持久化保存
- [ ] 支持删除资产

### Story 2: 打开首页追踪行情

**As a** 投资者
**I want to** 每次打开首页都看到最新价格与涨跌幅
**So that** 我能快速判断当日变化

**Acceptance Criteria:**
- [ ] 每次访问首页，服务端对每个资产发起一次行情抓取（允许带短 TTL 缓存）
- [ ] 展示：价格、涨跌幅、数据时间
- [ ] 当行情获取失败时明确提示，不影响页面整体渲染

### Story 3: 再平衡提醒

**As a** 投资者
**I want to** 当某资产权重超出阈值时收到提醒
**So that** 我能及时进行再配置/再平衡

**Acceptance Criteria:**
- [ ] 计算市值 = 持仓数量 * 价格（或净值估算）
- [ ] 计算权重 = 市值 / 总市值
- [ ] 若权重 < 最小阈值 或 > 最大阈值，则触发提醒并标记该资产

---

## Functional Requirements

### Core Features

**Feature 1: 资产管理**
- Description: 管理资产列表与再平衡参数
- User flow: 资产设置页新增/编辑/删除 -> 保存到本地文件
- Edge cases: 目标占比和不为 1；持仓为 0；阈值不合理（min>max）
- Error handling: 表单校验；保存失败提示

**Feature 2: 行情抓取**
- Description: 支持中国 A 股/ETF 的价格与涨跌幅；支持常见场外基金净值估算
- User flow: 首页访问 -> 后端批量抓取 -> 聚合展示
- Edge cases: 数据源不可用/字段变更；代码歧义（如 `000001`）
- Error handling: 单资产失败不影响其他资产；页面显示“行情获取失败”

**Feature 3: 再平衡判定**
- Description: 以“四类资产桶权重阈值区间”作为触发条件（默认 15%~35%，目标各 25%）
- User flow: 首页计算权重 -> 输出提醒列表
- Edge cases: 总市值=0；部分资产价格缺失
- Error handling: 总市值为 0 时占比为 0 并提示用户完善持仓

**Feature 4: 拖动分配到四类桶**
- Description: 在资产设置页把资产拖动到 4 个桶中，保存分配关系
- User flow: 拖动卡片 -> 服务端持久化 -> 概览页按桶聚合展示
- Edge cases: 未分配资产；重复拖动；网络失败
- Error handling: 失败提示/重试；未分配资产在概览与邮件中标记

**Feature 5: 链上资产（MVP：EVM）**
- Description: 通过钱包地址读取原生币/ERC20 余额，并用 CoinGecko 获取价格与 24h 涨跌幅
- User flow: 配置链、钱包、token 合约与 CoinGecko id -> 首页与定时任务抓取 -> 纳入权重计算
- Edge cases: RPC 不可用/限流；代币 decimals/symbol 解析失败；价格 id 不存在
- Error handling: 单资产失败不影响整体；在页面与邮件中标注数据错误来源

### Out of Scope（本阶段不做）
- 用户登录/多用户
- 自动下单/自动交易
- 推送通知：短信/微信/手机推送（本阶段只做邮件）
- 直接对接支付宝/蚂蚁财富持仓与行情（无公开接口；抓取风险高）
- 历史曲线/收益率分析

---

## Technical Constraints

### Performance
- 首页渲染（含行情抓取）：P95 < 2.5s
- 单次访问最多资产数（MVP）：建议 ≤ 30

### Security
- 默认本地运行，单机单用户，无需账户系统
- 不收集个人身份信息

### Integration
- 行情数据源：公开网页接口（非官方），需要容错与缓存

### Technology Stack（MVP 实现）
- Python 3.12
- FastAPI + Jinja2（服务端渲染：一次页面请求完成一次追踪）
- 本地 JSON 文件持久化（后续可升级 SQLite）

---

## MVP Scope & Phasing

### Phase 1: MVP（已实现/进行中）
- 资产管理（增删改）
- 首页追踪（价格、涨跌幅、数据时间）
- 权重计算与阈值提醒

### Phase 2: Enhancements
- 历史记录（每日快照）与趋势图
- 更明确的“再平衡建议”（需要买/卖多少份额）
- 数据源可配置与自动切换（多家行情源冗余）

---

## Risk Assessment

| Risk | Probability | Impact | Mitigation Strategy |
|------|------------|--------|---------------------|
| 行情接口变更/限流 | Med | High | TTL 缓存、容错解析、支持多数据源切换 |
| 代码歧义（基金/股票同码） | Med | Med | 支持 `sh/sz/bj` 前缀强制指定；UI 给出提示 |
| 用户输入参数不合理 | Med | Low | 表单校验与默认值；提示纠正 |

---

## Open Questions（需要你确认）

1. 你主要追踪的“场外 ETF/基金代码”是否以 **6 位基金代码**为主（例如 `161725`、`000001`）？是否需要同时覆盖 **港股/美股**？
2. 再平衡触发规则你希望用哪种口径？
   - A) 固定区间（默认 15%~35%）
   - B) 相对目标偏离（例如偏离目标 ±5 个百分点）
3. “提醒”的形式你希望是什么？
   - 只在页面展示
   - 需要桌面通知/邮件/微信（这会引入后台任务与推送集成）

补充（已确认/已实现）：
- 四类资产目标各 25%，阈值采用 15%~35%
- 邮件：每月第一个工作日固定提醒 + 超出阈值提醒（带冷却）
- 链上资产：MVP 先做 EVM；非 EVM（BTC 等）后续扩展

---

*This PRD is a draft to enable MVP delivery; we’ll iterate to 90+ score after clarifying the open questions.*
