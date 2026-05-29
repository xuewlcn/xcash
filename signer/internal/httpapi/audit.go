package httpapi

import (
	"bytes"
	"context"
	"encoding/json"
	"io"
	"strings"

	"github.com/gin-gonic/gin"

	"xcash-signer/internal/store"
)

// auditMiddleware 记录请求审计。注册为受保护组的最外层：
// 先读出 body（用于解析定位信息），执行链路，再据结果落审计。
//
// 记录规则（对齐原 Django 版）：
//   - 无 request_id 不记；
//   - /internal/* 只记失败（成功只读请求不混入主审计流，但鉴权失败需追溯枚举）；
//   - 重复 request_id 由 InsertAuditIfAbsent 静默去重。
func (s *Server) auditMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		body, _ := c.GetRawData()
		c.Request.Body = io.NopCloser(bytes.NewReader(body))

		c.Next()

		s.recordAudit(c, body)
	}
}

func (s *Server) recordAudit(c *gin.Context, body []byte) {
	requestID := strings.TrimSpace(c.GetHeader(headerRequestID))
	if requestID == "" {
		return
	}

	status, errCode := auditOutcome(c)
	endpoint := c.Request.URL.Path
	isFailure := status != store.AuditSucceeded
	if strings.HasPrefix(endpoint, "/internal/") && !isFailure {
		return
	}

	meta := parseAuditMeta(body)
	rec := store.AuditRecord{
		RequestID:    requestID,
		Endpoint:     endpoint,
		WalletID:     meta.walletID,
		ChainType:    meta.chainType,
		BIP44Account: meta.bip44Account,
		AddressIndex: meta.addressIndex,
		RemoteIP:     remoteIP(c),
		Status:       status,
		ErrorCode:    errCode,
		Detail:       "",
	}
	// 审计失败不应影响主请求结果，吞掉错误（落不进审计是观测降级，不是业务失败）。
	_ = s.st.InsertAuditIfAbsent(context.Background(), rec)
}

// auditOutcome 根据上下文里的错误码推断审计状态。
func auditOutcome(c *gin.Context) (status, errorCode string) {
	v, ok := c.Get(ctxKeyErrorCode)
	if !ok {
		return store.AuditSucceeded, ""
	}
	code, _ := v.(string)
	if code == errRateLimit.code {
		return store.AuditRateLimited, code
	}
	return store.AuditFailed, code
}

type auditMeta struct {
	walletID     *int64
	chainType    string
	bip44Account *int64
	addressIndex *int64
}

// parseAuditMeta 从请求体宽松解析定位信息；解析失败或字段缺失时留空，不影响主流程。
func parseAuditMeta(body []byte) auditMeta {
	var raw struct {
		WalletID     *int64 `json:"wallet_id"`
		ChainType    string `json:"chain_type"`
		BIP44Account *int64 `json:"bip44_account"`
		AddressIndex *int64 `json:"address_index"`
	}
	_ = json.Unmarshal(body, &raw)

	m := auditMeta{walletID: raw.WalletID, chainType: raw.ChainType}
	// bip44_account / address_index 来自原始请求，可能非法（负数），仅在合法非负时记录。
	if raw.BIP44Account != nil && *raw.BIP44Account >= 0 {
		m.bip44Account = raw.BIP44Account
	}
	if raw.AddressIndex != nil && *raw.AddressIndex >= 0 {
		m.addressIndex = raw.AddressIndex
	}
	return m
}
