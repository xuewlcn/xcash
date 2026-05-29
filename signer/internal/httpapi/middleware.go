package httpapi

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"io"
	"net"
	"strings"

	"github.com/gin-gonic/gin"
)

const (
	headerRequestID = "X-Signer-Request-Id"
	headerSignature = "X-Signer-Signature"

	// 上下文键：鉴权通过后存入 request_id，供后续 handler / 审计使用。
	ctxKeyRequestID = "request_id"
	// 上下文键：abortError 写入错误码，供审计中间件判定 failed / rate_limited。
	ctxKeyErrorCode = "error_code"
)

// signaturePayload 构造 HMAC 签名材料：METHOD\npath\nrequest_id\n<原始 body>。
// 必须与主应用客户端 build_signer_signature_payload 完全一致。
func signaturePayload(method, path, requestID string, body []byte) []byte {
	var b bytes.Buffer
	b.WriteString(strings.ToUpper(method))
	b.WriteByte('\n')
	b.WriteString(path)
	b.WriteByte('\n')
	b.WriteString(requestID)
	b.WriteByte('\n')
	b.Write(body)
	return b.Bytes()
}

// rateLimitMiddleware 按 (endpoint, 来源 IP) 做固定窗口限流，DEBUG 下跳过。
// 注册在鉴权之前，使未通过鉴权的洪泛也先被限流，保护 HMAC 计算不被打爆。
func (s *Server) rateLimitMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if s.cfg.Debug {
			c.Next()
			return
		}
		key := c.Request.URL.Path + ":" + remoteIP(c)
		if !s.ipLimiter.Allow(key) {
			abortError(c, errRateLimit, "")
			return
		}
		c.Next()
	}
}

// authMiddleware 校验 HMAC 鉴权头并做重放防护。
func (s *Server) authMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		if s.cfg.SharedSecret == "" {
			abortError(c, errAccessDeny, "signer 未配置共享密钥")
			return
		}

		// 必须对原始 body 字节算 HMAC：先读出，再回填供后续 handler 绑定。
		body, err := c.GetRawData()
		if err != nil {
			body = nil
		}
		c.Request.Body = io.NopCloser(bytes.NewReader(body))

		requestID := strings.TrimSpace(c.GetHeader(headerRequestID))
		signature := strings.TrimSpace(c.GetHeader(headerSignature))
		if requestID == "" || signature == "" {
			abortError(c, errParameter, "缺少 signer 鉴权头")
			return
		}

		mac := hmac.New(sha256.New, []byte(s.cfg.SharedSecret))
		mac.Write(signaturePayload(c.Request.Method, c.Request.URL.Path, requestID, body))
		expected := hex.EncodeToString(mac.Sum(nil))
		// 常量时间比较，避免计时侧信道。
		if !hmac.Equal([]byte(signature), []byte(expected)) {
			abortError(c, errSignature, "")
			return
		}

		// 重放防护：同一 request_id 在 TTL 内只接受一次。
		if !s.replay.CheckAndMark(requestID) {
			abortError(c, errReplay, "")
			return
		}

		c.Set(ctxKeyRequestID, requestID)
		c.Next()
	}
}

// remoteIP 取直连对端 IP（对齐原 Django 的 REMOTE_ADDR），不信任 XFF，避免被伪造绕过限流。
func remoteIP(c *gin.Context) string {
	host, _, err := net.SplitHostPort(c.Request.RemoteAddr)
	if err != nil {
		return c.Request.RemoteAddr
	}
	return host
}
