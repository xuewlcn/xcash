-- signer 数据库 schema（SQLite）。SQL 即真值源，开机以 CREATE TABLE IF NOT EXISTS 幂等应用，
-- 不使用迁移文件。wallet/address 表结构已冻结：扩展新链只改派生代码，不改这里。

CREATE TABLE IF NOT EXISTS signer_wallet (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 主应用侧钱包 ID，全局唯一，是跨系统对账的锚点
    xcash_wallet_id    INTEGER NOT NULL UNIQUE,
    -- 助记词密文（AES-256-GCM，见 internal/crypto）；一份助记词可派生所有链，故本表链中立
    encrypted_mnemonic TEXT    NOT NULL,
    created_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    updated_at         TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS signer_address (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    wallet_id     INTEGER NOT NULL REFERENCES signer_wallet (id) ON DELETE CASCADE,
    -- 链族标识（evm / bitcoin / solana…）；必要时把脚本类型编码进来，如 bitcoin_taproot
    chain_type    TEXT    NOT NULL,
    -- HD 路径两个可变层级的通用槽位（不绑定 BIP44 语义）：
    --   EVM  m/44'/60'/{account}'/0/{index}
    --   BTC  m/84'/0'/{account}'/0/{index}
    --   SOL  m/44'/501'/{account}'/0'（index 通常填 0）
    bip44_account INTEGER NOT NULL,
    address_index INTEGER NOT NULL,
    -- 规范化后的地址（EVM 存 EIP-55 校验和；其余链存各自规范形式），区分大小写
    address       TEXT    NOT NULL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    -- 同一派生身份（钱包+链+account+index）唯一映射到同一地址
    UNIQUE (wallet_id, chain_type, bip44_account, address_index),
    -- 一个地址在一条链上唯一；该唯一索引同时服务 is_internal_address 的 (chain, address) 点查
    UNIQUE (chain_type, address)
);

-- 请求审计：只写不改，记录定位 + 结果 + 错误码，不含助记词/私钥/原始交易。
CREATE TABLE IF NOT EXISTS signer_request_audit (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id    TEXT    NOT NULL UNIQUE,
    endpoint      TEXT    NOT NULL,
    wallet_id     INTEGER,
    chain_type    TEXT    NOT NULL DEFAULT '',
    bip44_account INTEGER,
    address_index INTEGER,
    remote_ip     TEXT    NOT NULL DEFAULT '',
    status        TEXT    NOT NULL CHECK (status IN ('succeeded', 'failed', 'rate_limited')),
    error_code    TEXT    NOT NULL DEFAULT '',
    detail        TEXT    NOT NULL DEFAULT '',
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- 服务 admin-summary 的近一小时聚合与近期异常查询。
CREATE INDEX IF NOT EXISTS idx_audit_endpoint_status_time
    ON signer_request_audit (endpoint, status, created_at);

