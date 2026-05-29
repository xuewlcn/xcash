package store

import (
	"context"
	"database/sql"
	"time"
)

// 审计状态值，与 schema 的 CHECK 约束一致。
const (
	AuditSucceeded   = "succeeded"
	AuditFailed      = "failed"
	AuditRateLimited = "rate_limited"
)

// AuditRecord 是写入审计的入参；可空字段用指针表示 NULL。
type AuditRecord struct {
	RequestID    string
	Endpoint     string
	WalletID     *int64
	ChainType    string
	BIP44Account *int64
	AddressIndex *int64
	RemoteIP     string
	Status       string
	ErrorCode    string
	Detail       string
}

// AuditRow 是审计读出结构，json tag 与原 Python 版 admin-summary 输出字段一致。
type AuditRow struct {
	RequestID    string `json:"request_id"`
	Endpoint     string `json:"endpoint"`
	WalletID     *int64 `json:"wallet_id"`
	ChainType    string `json:"chain_type"`
	BIP44Account *int64 `json:"bip44_account"`
	AddressIndex *int64 `json:"address_index"`
	Status       string `json:"status"`
	ErrorCode    string `json:"error_code"`
	Detail       string `json:"detail"`
	CreatedAt    string `json:"created_at"`
}

// RequestSummary 是近一小时请求聚合。
type RequestSummary struct {
	Total       int64
	Succeeded   int64
	Failed      int64
	RateLimited int64
}

// InsertAuditIfAbsent 写入一条审计；request_id 已存在则静默跳过（只写不改，保证取证完整）。
func (s *Store) InsertAuditIfAbsent(ctx context.Context, rec AuditRecord) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO signer_request_audit
			(request_id, endpoint, wallet_id, chain_type, bip44_account, address_index, remote_ip, status, error_code, detail)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON CONFLICT (request_id) DO NOTHING`,
		rec.RequestID, rec.Endpoint, nullInt(rec.WalletID), rec.ChainType,
		nullInt(rec.BIP44Account), nullInt(rec.AddressIndex), rec.RemoteIP,
		rec.Status, rec.ErrorCode, truncate(rec.Detail, 255),
	)
	return err
}

// CountWallets 返回钱包总数。
func (s *Store) CountWallets(ctx context.Context) (int64, error) {
	var n int64
	err := s.db.QueryRowContext(ctx, `SELECT COUNT(*) FROM signer_wallet`).Scan(&n)
	return n, err
}

// RequestSummaryLastHour 聚合近一小时 /v1/ 端点的请求结果。
// 阈值由 Go 计算并以与 created_at 相同的 ISO8601 格式传入，保证字符串比较即时间比较。
func (s *Store) RequestSummaryLastHour(ctx context.Context) (RequestSummary, error) {
	threshold := time.Now().UTC().Add(-time.Hour).Format("2006-01-02T15:04:05.000Z")
	var sm RequestSummary
	err := s.db.QueryRowContext(ctx, `
		SELECT
			COUNT(*),
			COALESCE(SUM(CASE WHEN status = 'succeeded'    THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN status = 'failed'       THEN 1 ELSE 0 END), 0),
			COALESCE(SUM(CASE WHEN status = 'rate_limited' THEN 1 ELSE 0 END), 0)
		FROM signer_request_audit
		WHERE endpoint LIKE '/v1/%' AND created_at >= ?`,
		threshold,
	).Scan(&sm.Total, &sm.Succeeded, &sm.Failed, &sm.RateLimited)
	return sm, err
}

// RecentAnomalies 返回最近的 /v1/ 异常（失败/限流）审计，供运营观测。
func (s *Store) RecentAnomalies(ctx context.Context, limit int) ([]AuditRow, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT request_id, endpoint, wallet_id, chain_type, bip44_account, address_index,
		       status, error_code, detail, created_at
		FROM signer_request_audit
		WHERE endpoint LIKE '/v1/%' AND status IN ('failed', 'rate_limited')
		ORDER BY created_at DESC
		LIMIT ?`,
		limit,
	)
	if err != nil {
		return nil, err
	}
	defer rows.Close()

	out := make([]AuditRow, 0, limit)
	for rows.Next() {
		var r AuditRow
		var walletID, bip44, addrIdx sql.NullInt64
		if err := rows.Scan(
			&r.RequestID, &r.Endpoint, &walletID, &r.ChainType, &bip44, &addrIdx,
			&r.Status, &r.ErrorCode, &r.Detail, &r.CreatedAt,
		); err != nil {
			return nil, err
		}
		r.WalletID = nullInt64ToPtr(walletID)
		r.BIP44Account = nullInt64ToPtr(bip44)
		r.AddressIndex = nullInt64ToPtr(addrIdx)
		out = append(out, r)
	}
	return out, rows.Err()
}

// nullInt 把 *int64 转为可直接传给驱动的值：nil → NULL。
func nullInt(p *int64) any {
	if p == nil {
		return nil
	}
	return *p
}

func nullInt64ToPtr(n sql.NullInt64) *int64 {
	if !n.Valid {
		return nil
	}
	v := n.Int64
	return &v
}

func truncate(s string, max int) string {
	if len(s) <= max {
		return s
	}
	return s[:max]
}
