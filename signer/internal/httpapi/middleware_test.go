package httpapi

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"database/sql"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	_ "modernc.org/sqlite"

	"xcash-signer/internal/config"
	"xcash-signer/internal/store"
	"xcash-signer/internal/throttle"
)

const testSecret = "test-shared-secret"

func newTestServer(t *testing.T, cfg config.Config) *Server {
	t.Helper()
	db, err := sql.Open("sqlite", filepath.Join(t.TempDir(), "t.sqlite"))
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	db.SetMaxOpenConns(1)
	t.Cleanup(func() { db.Close() })
	return New(cfg, store.New(db))
}

// protectedEngine 装配「限流 → 鉴权 → dummy handler」，模拟受保护端点。
func protectedEngine(s *Server) *gin.Engine {
	gin.SetMode(gin.TestMode)
	r := gin.New()
	g := r.Group("")
	g.Use(s.rateLimitMiddleware(), s.authMiddleware())
	g.POST("/v1/echo", func(c *gin.Context) { c.JSON(http.StatusOK, gin.H{"ok": true}) })
	return r
}

func clientSign(secret, method, path, reqID string, body []byte) string {
	mac := hmac.New(sha256.New, []byte(secret))
	mac.Write(signaturePayload(method, path, reqID, body))
	return hex.EncodeToString(mac.Sum(nil))
}

// do 发一个 POST /v1/echo 请求，可选带鉴权头。
func do(engine *gin.Engine, reqID, signature string, body []byte) *httptest.ResponseRecorder {
	req := httptest.NewRequest(http.MethodPost, "/v1/echo", bytes.NewReader(body))
	if reqID != "" {
		req.Header.Set(headerRequestID, reqID)
	}
	if signature != "" {
		req.Header.Set(headerSignature, signature)
	}
	rec := httptest.NewRecorder()
	engine.ServeHTTP(rec, req)
	return rec
}

func codeOf(t *testing.T, rec *httptest.ResponseRecorder) string {
	t.Helper()
	var resp map[string]any
	if err := json.Unmarshal(rec.Body.Bytes(), &resp); err != nil {
		return ""
	}
	code, _ := resp["code"].(string)
	return code
}

func TestAuthValidRequestPasses(t *testing.T) {
	s := newTestServer(t, config.Config{Debug: true, SharedSecret: testSecret})
	engine := protectedEngine(s)
	body := []byte(`{"wallet_id":1}`)
	sig := clientSign(testSecret, http.MethodPost, "/v1/echo", "r1", body)

	rec := do(engine, "r1", sig, body)
	if rec.Code != http.StatusOK {
		t.Fatalf("有效请求应 200，实际 %d (%s)", rec.Code, rec.Body.String())
	}
}

func TestAuthMissingHeaders(t *testing.T) {
	s := newTestServer(t, config.Config{Debug: true, SharedSecret: testSecret})
	engine := protectedEngine(s)

	rec := do(engine, "", "", []byte(`{}`))
	if rec.Code != http.StatusBadRequest || codeOf(t, rec) != "1000" {
		t.Fatalf("缺鉴权头应 400/1000，实际 %d/%s", rec.Code, codeOf(t, rec))
	}
}

func TestAuthBadSignature(t *testing.T) {
	s := newTestServer(t, config.Config{Debug: true, SharedSecret: testSecret})
	engine := protectedEngine(s)

	rec := do(engine, "r1", "deadbeef", []byte(`{}`))
	if rec.Code != http.StatusForbidden || codeOf(t, rec) != "1003" {
		t.Fatalf("错误签名应 403/1003，实际 %d/%s", rec.Code, codeOf(t, rec))
	}
}

func TestAuthReplayRejected(t *testing.T) {
	s := newTestServer(t, config.Config{Debug: true, SharedSecret: testSecret})
	engine := protectedEngine(s)
	body := []byte(`{"wallet_id":1}`)
	sig := clientSign(testSecret, http.MethodPost, "/v1/echo", "same-id", body)

	if rec := do(engine, "same-id", sig, body); rec.Code != http.StatusOK {
		t.Fatalf("首次应 200，实际 %d", rec.Code)
	}
	rec := do(engine, "same-id", sig, body)
	if rec.Code != http.StatusBadRequest || codeOf(t, rec) != "1009" {
		t.Fatalf("重放应 400/1009，实际 %d/%s", rec.Code, codeOf(t, rec))
	}
}

func TestAuthSharedSecretNotConfigured(t *testing.T) {
	s := newTestServer(t, config.Config{Debug: true, SharedSecret: ""})
	engine := protectedEngine(s)

	rec := do(engine, "r1", "whatever", []byte(`{}`))
	if rec.Code != http.StatusForbidden || codeOf(t, rec) != "1005" {
		t.Fatalf("未配置共享密钥应 403/1005，实际 %d/%s", rec.Code, codeOf(t, rec))
	}
}

func TestRateLimitExceeded(t *testing.T) {
	// Debug=false 才启用限流；把 IP 限流器换成小额度便于触发。
	s := newTestServer(t, config.Config{Debug: false, SharedSecret: testSecret})
	s.ipLimiter = throttle.NewLimiter(2, time.Minute)
	engine := protectedEngine(s)

	body := []byte(`{}`)
	for i, reqID := range []string{"a", "b"} {
		sig := clientSign(testSecret, http.MethodPost, "/v1/echo", reqID, body)
		if rec := do(engine, reqID, sig, body); rec.Code != http.StatusOK {
			t.Fatalf("第 %d 次应 200，实际 %d", i+1, rec.Code)
		}
	}
	// 第 3 次超 IP 限额，在鉴权之前被拦。
	sig := clientSign(testSecret, http.MethodPost, "/v1/echo", "c", body)
	rec := do(engine, "c", sig, body)
	if rec.Code != http.StatusTooManyRequests || codeOf(t, rec) != "1010" {
		t.Fatalf("超限应 429/1010，实际 %d/%s", rec.Code, codeOf(t, rec))
	}
}
