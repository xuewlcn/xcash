# VaultSlot Factory 自部署与归集/隔离方案

## 背景

当前 Xcash 的 VaultSlot 模型是非托管支付网关设计：收款地址由 Factory 以确定性方式部署，资金流向在 VaultSlot 创建时写入合约不可变参数。任何人都可以调用 `collect(token)` 触发归集，调用方只承担 Gas / Energy / Bandwidth，资金只能进入项目配置的归集地址。

这个模型适合自部署场景，但作为开放 SaaS 给商户使用时，有几个需要补齐的能力：

- 平台应自行部署并锁定 Factory / Implementation，避免长期依赖上游链上合约地址。
- 商户项目需要配置正常归集地址与风险隔离地址。
- 收到资金后，系统应能根据风控结果选择“正常归集”或“风险隔离”。
- 商户注册、项目创建、项目名称、域名、收单页面展示需要产品化。
- 系统代付部署与归集/隔离 Gas 时，需要有商户计费、冻结、欠费限制链路。

## 设计目标

- 平台拥有自己的 Factory / Implementation 合约地址，并在部署配置中显式锁定。
- 每个项目按链类型配置两个不可变资金流向：
  - `vault`：正常归集地址。
  - `risk_vault`：风险隔离地址。
- VaultSlot 合约提供两个资金动作：
  - `collect(token)`：正常归集到 `vault`。
  - `isolate(token)`：风险隔离到 `risk_vault`。
- 两个动作都不允许调用方指定收款人，资金流向只能来自合约不可变参数。
- 平台后端根据 AML / 风控结果决定调度 `collect` 还是 `isolate`。
- 欠费商户不能创建新账单、新充值地址、不能由平台继续代付部署/归集资源。
- 已部署 VaultSlot 的链上资金不可被平台冻结或改道，这一点必须作为产品边界明确披露。

## 非目标

- 不做托管资金池。
- 不通过后台状态冻结已部署 VaultSlot 的链上资金。
- 不允许平台在链上单方面改写商户资金流向。
- 不在第一版做合约可升级代理；资金合约应保持不可升级、极简、可验证。
- 不尝试隐藏地址预测算法；开源代码下算法不是商业护城河。

## 自部署 Factory / Implementation

### 合约资产

当前仓库已有 Tron 合约源码：

- `xcash/tron/contracts/src/XcashVaultSlot.sol`
- `xcash/tron/contracts/src/XcashVaultSlotFactory.sol`
- `xcash/tron/contracts/src/OpenZeppelinClones.sol`

EVM 合约源码在：

- `xcash/evm/contracts/src/XcashVaultSlot.sol`
- `xcash/evm/contracts/src/XcashVaultSlotFactory.sol`

平台需要自行编译、部署并验证：

1. 部署 `XcashVaultSlot` implementation。
2. 使用 implementation 地址部署 `XcashVaultSlotFactory`。
3. 在链上浏览器完成源码验证。
4. 将地址写入运行配置或数据库，不再依赖上游默认常量。

### 配置方式

建议从“代码常量”改为“系统配置 + 链配置”：

- `Chain.vault_slot_factory_address`
- `Chain.vault_slot_implementation_address`
- `Chain.vault_slot_contract_version`

原因：

- 不同部署方应该有自己的合约地址。
- 后续合约升级应以版本形式并存，不能直接覆盖旧版本。
- 已创建的 VaultSlot 必须记录自己使用的合约版本，避免新旧 Factory 混用。

### 版本并存

新增 `VaultSlotContractDeployment` 模型：

| 字段 | 含义 |
| --- | --- |
| `chain` | 链 |
| `version` | 合约版本，例如 `v1`, `v2-isolation` |
| `factory_address` | Factory 地址 |
| `implementation_address` | Implementation 地址 |
| `source_hash` | 合约源码/编译产物摘要 |
| `active` | 是否用于新地址 |
| `created_at` | 创建时间 |

`VaultSlot` 记录增加：

- `contract_version`
- `factory_address`
- `implementation_address`
- `normal_vault`
- `risk_vault`

这样未来上线新合约时，旧地址仍按旧版本归集，新地址按新版本创建。

## 新 VaultSlot 合约设计

### 不可变参数

现有 VaultSlot 只写入一个 `vault`。新版本应写入两个地址：

- `vault`
- `riskVault`

clone immutable args 编码建议：

```text
abi.encodePacked(vault, riskVault)
```

合约读取时要求参数长度为 40 bytes。

### 方法设计

```solidity
function collect(address token) external;
function isolate(address token) external;
function vault() public view returns (address payable);
function riskVault() public view returns (address payable);
```

语义：

- `collect(address(0))`：归集原生币到 `vault`。
- `collect(token)`：归集 TRC20 / ERC20 到 `vault`。
- `isolate(address(0))`：隔离原生币到 `riskVault`。
- `isolate(token)`：隔离 TRC20 / ERC20 到 `riskVault`。

安全约束：

- `vault` 和 `riskVault` 都不能为空。
- `collect` 和 `isolate` 都不接受 recipient 参数。
- 不加 owner、pause、upgrade。
- 不加平台可改费率或可改地址入口。
- 保持 permissionless，任何人可调用，但不能改变资金流向。

### Factory 方法

```solidity
function deployVaultSlot(
    address payable vault,
    address payable riskVault,
    bytes32 salt
) external returns (address vaultSlot);
```

事件：

```solidity
event XcashVaultSlotDeployed(
    address indexed vaultSlot,
    address indexed vault,
    address indexed riskVault,
    bytes32 salt
);
```

地址预测算法必须同步更新，因为 init code / immutable args 变化后，同一 salt 预测出的地址会变化。

## 项目配置改造

### 项目字段

当前项目已有 EVM / Tron 归集地址。需要增加可选隔离钱包地址：

- `evm_risk_vault`
- `tron_risk_vault`

也建议重命名展示口径：

- `evm_vault` -> EVM 正常归集地址
- `tron_vault` -> Tron 正常归集地址
- `evm_risk_vault` -> EVM 风险隔离地址
- `tron_risk_vault` -> Tron 风险隔离地址

### 可选策略

第一版建议隔离地址“可选但有明确降级规则”：

- 未配置 `risk_vault` 时，项目不能启用“自动风险隔离”。
- 未配置 `risk_vault` 时，高风险资金默认不自动归集，进入人工处理状态。
- 管理后台给出项目就绪检查提示。

不要默认把风险资金也归集到正常地址，否则隔离功能形同虚设。

### 不可变性

一旦项目已创建任何 VaultSlot：

- 正常归集地址不可修改。
- 风险隔离地址不可修改。

如果必须换地址，应创建新项目或新合约版本，不改旧地址流向。

## 归集与隔离调度

### 当前链路

当前确认入账后会创建 `VaultSlotCollectSchedule`，到期后创建 `VaultSlotCollect` 链上任务。

### 新链路

引入资金动作类型：

```text
VaultSlotFundAction = collect | isolate
```

计划表可扩展为：

- `VaultSlotFundSchedule`
  - `vault_slot`
  - `chain`
  - `crypto`
  - `action`
  - `due_at`
  - `tx_task`

或者保守一点，在现有 `VaultSlotCollectSchedule` 增加 `action` 字段。

建议新建表，避免“collect”命名污染隔离语义。

### 决策规则

入账确认后：

1. 如果 AML 未启用：创建 `collect` 计划。
2. 如果 AML 启用但结果未出：进入待风控状态，不立即归集。
3. 风险低/中且允许放行：创建 `collect` 计划。
4. 风险高且项目配置了 `risk_vault`：创建 `isolate` 计划。
5. 风险高但项目未配置 `risk_vault`：不创建链上任务，进入人工处理。

### 人工处理动作

管理后台应支持：

- 放行到正常归集地址：创建 `collect` 计划。
- 隔离到风险地址：创建 `isolate` 计划。
- 标记外部已处理：不再自动调度。

这些动作都必须只面向超管或具备资金治理权限的角色。

## 商户前台与项目创建

### 商户注册

新增商户实体：

- `Merchant`
  - 名称
  - 登录账号
  - 状态：试用、正常、欠费、冻结、关闭
  - 余额/信用额度
  - 套餐
  - 创建时间

项目归属到商户：

- `Project.merchant`

未来后台可以区分：

- 平台超管后台
- 商户控制台

### 商户可新增项目

商户新增项目时需要填写：

- 项目名称
- 项目域名
- 通知地址
- IP 白名单
- 正常归集地址
- 风险隔离地址，可选
- 是否启用 EPay 兼容
- 账单收款模式：钱包直收 / 智能合约
- Tron / EVM 链选择

项目创建后由系统生成：

- Appid
- HMAC 密钥
- EPay pid/key，如启用

## 收单页面展示

当前支付页左上角容易显示默认品牌。后续应明确拆分：

- 平台品牌：Xcash / 平台自有品牌。
- 商户项目名称：对付款人展示的收款主体。
- 项目域名：用于增强付款人识别。

支付页应展示：

- 项目名称
- 项目域名或商户站点
- 订单名称
- 金额
- 币种/链
- 收款地址
- 风险提示

展示规则：

- H1 或核心标题优先显示项目名称。
- 平台品牌可以放页脚或次级位置。
- 项目域名必须来自 `Project.domain`，不能从请求 Host 临时推断。
- 域名需要后台校验，避免商户冒用其他品牌。

建议新增字段：

- `Project.display_name`
- `Project.domain`
- `Project.logo`
- `Project.support_url`

第一版可以只做 `display_name` 和 `domain`。

## GAS / Energy 计费链路

### 成本类型

平台会为商户代付这些链上成本：

- VaultSlot 部署成本
- 正常归集 `collect` 成本
- 风险隔离 `isolate` 成本
- 失败重试成本
- Tron Energy 租赁或质押占用成本
- RPC / 节点请求成本

### 计费原则

每个链上任务成功终局后记录真实成本：

- EVM：`gas_used * effective_gas_price`
- Tron：实际 Energy / Bandwidth 消耗折算，或按资源市场租赁成本折算

成本账单应关联：

- merchant
- project
- chain
- tx_task
- action
- tx_hash
- native_cost_amount
- usd_cost_amount
- service_fee_amount
- total_amount

建议新建：

- `MerchantBalance`
- `MerchantLedgerEntry`
- `MerchantGasCharge`

### 预扣与后扣

推荐两段式：

1. 创建链上任务前预检商户余额。
2. 任务成功后按真实成本结算。

对于部署任务：

- 余额不足时不创建新 VaultSlot 部署任务。
- 已收款但未部署的地址会停留在“待资源/余额处理”状态。

对于归集/隔离任务：

- 正常模式下余额不足不自动代付。
- 高风险隔离可配置为平台兜底执行，避免风险资金长期留在收款地址。

### 欠费限制

商户欠费或余额不足时限制：

- 禁止创建新项目。
- 禁止创建新账单。
- 禁止创建新充值地址。
- 禁止自动部署新 VaultSlot。
- 禁止平台自动归集非风险资金。
- API 查询可保留只读能力。
- Webhook 可按套餐策略保留一定时间，避免商户对账断裂。

不能限制：

- 已部署 VaultSlot 的链上 `collect/isolate` 被别人调用。
- 已暴露地址继续收到链上转账。
- 商户自行调用链上合约。

### Tron 特殊处理

当前系统要求发送地址 Energy 足够才广播，不用 TRX 余额兜底燃烧 Energy。SaaS 化后建议明确资源策略：

- 平台统一租赁 Energy 给系统热钱包。
- 按任务实际消耗或估算消耗向商户计费。
- 商户余额不足时，不继续为其部署/归集。
- 系统热钱包资源水位不足时，进入运营告警。

如果未来允许 Energy 不足时燃烧 TRX，需要改 `tron.resources` 的本地资源闸门，并重新设计成本上限。

## 状态机建议

### 项目状态

```text
draft
ready
suspended
arrears
closed
```

### VaultSlot 资金处理状态

```text
received
risk_pending
collect_scheduled
isolate_scheduled
deploy_pending
tx_submitted
fund_moved
manual_required
failed
```

### 商户余额状态

```text
normal
low_balance
insufficient
overdue
frozen
```

## 迁移路线

### 第一阶段：平台自部署合约

- 部署自有 Factory / Implementation。
- 新增合约部署配置表。
- 新地址使用自有 Factory。
- 旧地址继续沿用旧 Factory，不迁移链上地址。

### 第二阶段：项目隔离地址

- 项目增加 `risk_vault` 字段。
- 后台项目就绪检查增加风险隔离检查。
- API 输出项目能力时包含是否支持风险隔离。

### 第三阶段：合约 v2

- 实现双地址 VaultSlot。
- 实现 `collect` / `isolate`。
- 更新地址预测。
- 更新部署任务 intent。
- Tron / EVM 分别完成测试网验收。

### 第四阶段：调度与风控联动

- 引入 fund action schedule。
- AML 结果驱动 collect/isolate。
- 管理后台增加人工放行/隔离动作。

### 第五阶段：商户 SaaS

- 商户注册/登录。
- 商户项目创建。
- 套餐和余额。
- Gas 成本流水。
- 欠费限制。

### 第六阶段：收单页面品牌化

- 项目名称和域名展示。
- 商户 logo。
- 域名校验。
- 支付页品牌层级重构。

## 测试重点

合约测试：

- `collect(address(0))` 只能转到 `vault`。
- `collect(token)` 只能转到 `vault`。
- `isolate(address(0))` 只能转到 `riskVault`。
- `isolate(token)` 只能转到 `riskVault`。
- 零地址参数拒绝部署。
- 同 salt / 同 vault / 同 riskVault 地址确定性一致。
- 不同 riskVault 会生成不同地址。

后端测试：

- 项目未配置 risk vault 时，高风险资金进入人工处理。
- 项目配置 risk vault 时，高风险资金创建 isolate 计划。
- 低风险资金创建 collect 计划。
- 欠费商户不能创建新地址/新账单。
- 欠费不影响已确认资金的账务记录。
- 旧合约版本地址仍按旧逻辑归集。
- 新合约版本地址按新逻辑隔离。

并发测试：

- 同一 VaultSlot 同一币种只能有一个 pending 动作计划。
- collect/isolate 不能同时对同一余额重复建任务。
- 商户余额预扣必须行锁保护，避免并发透支。

## 风险与取舍

- `isolate` 是链上动作，隔离也需要 Gas；高风险资金越多，平台资源消耗越高。
- 已部署旧 VaultSlot 无法补充 risk vault，只能继续按旧规则归集。
- 如果把平台抽佣放进合约，会改变非托管信任模型，第一版不建议做。
- 如果商户自行调用链上 `collect/isolate`，平台无法阻止；平台只能控制 API、扫描、Webhook、资源代付与后台服务。
- 风险隔离地址也应由商户控制，平台不应托管私钥，否则产品性质会从非托管变成半托管/托管。

## 推荐结论

短期先做两件事：

1. 自部署 Factory / Implementation，并把合约地址从代码常量沉淀为可审计配置。
2. 在项目模型里增加风险隔离地址，为合约 v2 和 SaaS 风控链路做准备。

中期再上线 VaultSlot v2：

- `collect` 正常归集。
- `isolate` 风险隔离。
- 两个资金流向均来自项目不可变配置。

长期商业化重点放在链下服务计费：

- 地址创建
- 链上扫描
- Webhook
- AML
- 报表
- RPC
- Gas / Energy 代付

不要把“能冻结或改道商户链上资金”作为商业化能力；这与当前非托管安全模型冲突。
