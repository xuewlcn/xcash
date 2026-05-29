// Package store 是 signer 的持久化层：SQLite schema 应用 + wallet/address 仓储。
//
// 设计要点：
//   - SQL 即真值源，开机以 CREATE TABLE IF NOT EXISTS 幂等建表，不用迁移文件。
//   - 仓储方法只负责存取已规范化的数据；地址规范化、助记词加解密在上层（crypto）完成。
//   - 表结构冻结：扩展新链只改派生代码，不改本包。
package store

import (
	"context"
	"database/sql"
	_ "embed"
	"errors"
)

//go:embed schema.sql
var schemaSQL string

// 仓储层错误。上层据此映射到对应的 API 错误码。
var (
	// ErrWalletNotFound 表示按 xcash_wallet_id 找不到钱包。
	ErrWalletNotFound = errors.New("store: wallet not found")
	// ErrAddressDrift 表示同一派生身份读回的地址与本次派生结果不一致（数据漂移），必须拒绝继续。
	ErrAddressDrift = errors.New("store: derived address conflicts with stored address")
)

// Wallet 是 signer_wallet 的领域表示。
type Wallet struct {
	ID                int64
	XcashWalletID     int64
	EncryptedMnemonic string
}

// Store 封装数据库句柄，对外暴露仓储方法。
type Store struct {
	db *sql.DB
}

// New 用已打开的 *sql.DB 构造 Store。
func New(db *sql.DB) *Store {
	return &Store{db: db}
}

// Migrate 幂等应用 schema。开机调用一次。
func (s *Store) Migrate(ctx context.Context) error {
	_, err := s.db.ExecContext(ctx, schemaSQL)
	return err
}

// Ping 探测数据库连通性，供健康检查使用。
func (s *Store) Ping(ctx context.Context) error {
	return s.db.PingContext(ctx)
}

// CreateWalletIfAbsent 实现 get_or_create 语义：
// 钱包已存在则原样返回（created=false，绝不覆盖已有 encrypted_mnemonic）；
// 不存在则用传入密文创建（created=true）。encryptedMnemonic 由上层加密好后传入。
func (s *Store) CreateWalletIfAbsent(
	ctx context.Context, xcashWalletID int64, encryptedMnemonic string,
) (Wallet, bool, error) {
	res, err := s.db.ExecContext(ctx, `
		INSERT INTO signer_wallet (xcash_wallet_id, encrypted_mnemonic)
		VALUES (?, ?)
		ON CONFLICT (xcash_wallet_id) DO NOTHING`,
		xcashWalletID, encryptedMnemonic,
	)
	if err != nil {
		return Wallet{}, false, err
	}
	affected, err := res.RowsAffected()
	if err != nil {
		return Wallet{}, false, err
	}

	wallet, err := s.GetWallet(ctx, xcashWalletID)
	if err != nil {
		return Wallet{}, false, err
	}
	return wallet, affected > 0, nil
}

// GetWallet 按 xcash_wallet_id 加载钱包，不存在返回 ErrWalletNotFound。
func (s *Store) GetWallet(ctx context.Context, xcashWalletID int64) (Wallet, error) {
	var w Wallet
	err := s.db.QueryRowContext(ctx, `
		SELECT id, xcash_wallet_id, encrypted_mnemonic
		FROM signer_wallet
		WHERE xcash_wallet_id = ?`,
		xcashWalletID,
	).Scan(&w.ID, &w.XcashWalletID, &w.EncryptedMnemonic)
	if errors.Is(err, sql.ErrNoRows) {
		return Wallet{}, ErrWalletNotFound
	}
	if err != nil {
		return Wallet{}, err
	}
	return w, nil
}

// RegisterDerivedAddress 落库一条派生地址（get_or_create），并校验同一派生身份稳定映射到同一地址。
// walletID 是 signer_wallet.id；normalizedAddress 须由上层按链规范化后传入。
func (s *Store) RegisterDerivedAddress(
	ctx context.Context,
	walletID int64,
	chainType string,
	bip44Account, addressIndex int,
	normalizedAddress string,
) error {
	if _, err := s.db.ExecContext(ctx, `
		INSERT INTO signer_address (wallet_id, chain_type, bip44_account, address_index, address)
		VALUES (?, ?, ?, ?, ?)
		ON CONFLICT (wallet_id, chain_type, bip44_account, address_index) DO NOTHING`,
		walletID, chainType, bip44Account, addressIndex, normalizedAddress,
	); err != nil {
		return err
	}

	// 读回该派生身份的现存地址，与本次派生结果比对，发现漂移立即报错。
	var stored string
	err := s.db.QueryRowContext(ctx, `
		SELECT address FROM signer_address
		WHERE wallet_id = ? AND chain_type = ? AND bip44_account = ? AND address_index = ?`,
		walletID, chainType, bip44Account, addressIndex,
	).Scan(&stored)
	if err != nil {
		return err
	}
	if stored != normalizedAddress {
		return ErrAddressDrift
	}
	return nil
}

// IsInternalAddress 判定某链上的地址是否为 signer 派生过的系统内地址。
// normalizedAddress 须由上层按链规范化后传入（与落库时一致）。
func (s *Store) IsInternalAddress(
	ctx context.Context, chainType, normalizedAddress string,
) (bool, error) {
	var one int
	err := s.db.QueryRowContext(ctx, `
		SELECT 1 FROM signer_address
		WHERE chain_type = ? AND address = ?
		LIMIT 1`,
		chainType, normalizedAddress,
	).Scan(&one)
	if errors.Is(err, sql.ErrNoRows) {
		return false, nil
	}
	if err != nil {
		return false, err
	}
	return true, nil
}
