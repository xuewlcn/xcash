# Xcash Signer 服务契约（Go 重写版必须严格兼容）

本服务是 xcash 的独立签名服务，持有热钱包助记词，对外只提供地址派生与交易签名。
Go 版是对原 Django 版的 **drop-in 替换**：HTTP 边界（路径 / 请求体 / 响应体 / 鉴权 / 错误码）
必须逐字节兼容，主应用客户端 `xcash/chains/signer.py` 不得改动。

## 鉴权（HMAC）

- 请求头：`X-Signer-Request-Id`、`X-Signer-Signature`
- 签名材料（字节）：`METHOD\npath\nrequest_id\n<原始请求体字节>`（`\n` 连接）
- 算法：HMAC-SHA256(共享密钥)，输出小写十六进制；用常量时间比较
- **必须对原始请求体字节计算 HMAC**，不可反序列化后重新编码（客户端用紧凑 JSON
  `separators=(",",":")`, `ensure_ascii=True`）
- 重放保护：同一 `request_id` 在 TTL（60s）内只接受一次，重复返回 1009
- `request_id` 也会出现在 POST 请求体里（客户端附加），signer 从请求头取，体内忽略

## 端点

| 方法 | 路径 | 鉴权 | 请求体 | 响应体 |
|---|---|---|---|---|
| GET | `/healthz` | 否 | — | `{"ok": bool}`（200/503） |
| GET | `/internal/admin-summary` | 是 | — | `{health,wallets,requests_last_hour,recent_anomalies}` |
| POST | `/v1/wallets/create` | 是 | `{wallet_id}` | `{wallet_id,created}` |
| POST | `/v1/wallets/derive-address` | 是 | `{wallet_id,chain_type,bip44_account,address_index}` | `{address}` |
| POST | `/v1/sign/evm` | 是 | 上 + `{tx_dict}` | `{tx_hash,raw_transaction}`（小写 0x） |

## 校验

- `wallet_id >= 1`
- `bip44_account`：0..10（`SIGNER_MAX_BIP44_ACCOUNT`）
- `address_index`：0..100_000_000（`SIGNER_MAX_ADDRESS_INDEX`）
- `chain_type` ∈ {`evm`}
- `tx_dict` 必含：`chainId,nonce,from,to,value,data,gas,gasPrice`；`from`/`to` 校验和地址；
  `data` 为 `0x` 开头十六进制且长度 ≤ `2 + 64*20`
- 请求体大小 ≤ 64 KiB（最外层闸，先于鉴权读取；超限返回 1011/413，不受 DEBUG 影响）

## 签名策略（/v1/sign/evm，必须复刻）

1. 加载钱包（不存在则 1000）
2. 按路径派生地址，必须等于 `tx_dict.from`，否则 1005
3. 解析真实收款方：若 `data` 以 `0xa9059cbb`（ERC20 transfer）开头且长度恰为 138 字符，
   取 calldata 内地址；否则取 `tx_dict.to`
4. 收款方**非系统内地址**时，施加钱包级签名限流（30/60s）
5. 派生私钥，签 legacy EIP-155 交易（go-ethereum）；输出 `tx_hash`、`raw_transaction`

## 错误码（响应体 `{code,message,detail}`）

| code | message | HTTP |
|---|---|---|
| 1000 | 参数错误 | 400 |
| 1005 | 无访问权限 | 403 |
| 1003 | 签名错误 | 403 |
| 1009 | 请求重复 | 400 |
| 1010 | 请求过于频繁 | 429 |
| 1011 | 请求体过大 | 413 |

## 限流（DEBUG 下跳过）

- IP 级：120 次 / 60s（按 endpoint + ip）
- 钱包签名级：30 次 / 60s（按 endpoint + wallet_id），仅当收款方非内部地址时计

## HD 派生

- BIP39：24 词英文助记词；BIP44 路径 EVM = `m/44'/60'/account'/0/index`
- seed 生成**不带 passphrase**
- 地址输出为 EVM 校验和（EIP-55）格式
- 黄金向量见 `testdata/parity_vectors.json`（由原 Python 实现 bip_utils + eth-account 生成）

## 数据表（沿用冻结结构，改存 SQLite）

- `signer_wallet(xcash_wallet_id UNIQUE, encrypted_mnemonic, created_at, updated_at)`（无冻结状态概念）
- `signer_address(wallet_id, chain_type, bip44_account, address_index, address, created_at;
  UNIQUE(wallet,chain,acc,idx); UNIQUE(chain,address))`
- `signer_request_audit(request_id UNIQUE, endpoint, wallet_id, chain_type, bip44_account,
  address_index, remote_ip, status, error_code, detail, created_at)`

## 助记词加密

- 原 Django 版用 Fernet + PBKDF2。**因未投产、无存量密文，Go 版改用 AES-256-GCM + KDF**，
  不复刻 Fernet。存储 `base64(salt + nonce + ciphertext)`。

## 配置（env，来自 .env.signer）

- `SIGNER_SHARED_SECRET`、`SIGNER_MNEMONIC_ENCRYPTION_KEY`（生产必填）
- `SIGNER_DEBUG`（默认 false）、`SIGNER_DB_PATH`（默认 /data/signer.sqlite）、
  `SIGNER_LISTEN_ADDR`（默认 :8000，对应客户端 `SIGNER_BASE_URL=http://signer:8000`）

## 架构变更（相对 Django 版）

- PG → SQLite（WAL）；去掉 Redis（限流 + 重放改进程内）；单实例托管者，无 signer-db 容器。
