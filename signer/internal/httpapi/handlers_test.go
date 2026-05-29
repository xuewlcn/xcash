package httpapi

import (
	"bytes"
	"context"
	"database/sql"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"path/filepath"
	"sync/atomic"
	"testing"

	"github.com/gin-gonic/gin"
	_ "modernc.org/sqlite"

	"xcash-signer/internal/config"
	"xcash-signer/internal/store"
)

var reqCounter int64

func nextReqID() string {
	return fmt.Sprintf("req-%d", atomic.AddInt64(&reqCounter, 1))
}

// newMigratedServer 建一个已迁移 SQLite 的 Server（非 DEBUG，限流/鉴权全开）。
func newMigratedServer(t *testing.T) *Server {
	t.Helper()
	db, err := sql.Open("sqlite", filepath.Join(t.TempDir(), "t.sqlite")+"?_pragma=foreign_keys(ON)")
	if err != nil {
		t.Fatalf("open: %v", err)
	}
	db.SetMaxOpenConns(1)
	t.Cleanup(func() { db.Close() })
	st := store.New(db)
	if err := st.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return New(config.Config{
		Debug:          false,
		SharedSecret:   testSecret,
		MnemonicEncKey: "integration-test-high-entropy-key-aaaaaaaaaaaa",
	}, st)
}

// call 走完整 Router 发一个带合法 HMAC 的请求。
func call(t *testing.T, engine *gin.Engine, method, path string, bodyObj any) (*httptest.ResponseRecorder, map[string]any) {
	t.Helper()
	var body []byte
	if bodyObj != nil {
		body, _ = json.Marshal(bodyObj)
	}
	reqID := nextReqID()
	req := httptest.NewRequest(method, path, bytes.NewReader(body))
	req.Header.Set(headerRequestID, reqID)
	req.Header.Set(headerSignature, clientSign(testSecret, method, path, reqID, body))
	rec := httptest.NewRecorder()
	engine.ServeHTTP(rec, req)

	var resp map[string]any
	_ = json.Unmarshal(rec.Body.Bytes(), &resp)
	return rec, resp
}

func TestCreateDeriveSignFlow(t *testing.T) {
	engine := newMigratedServer(t).Router()

	// 创建钱包：首次 created=true
	rec, resp := call(t, engine, http.MethodPost, "/v1/wallets/create", gin.H{"wallet_id": 1})
	if rec.Code != 200 || resp["created"] != true {
		t.Fatalf("创建应 200/created=true，实际 %d %v", rec.Code, resp)
	}
	// 幂等：再次 created=false
	_, resp = call(t, engine, http.MethodPost, "/v1/wallets/create", gin.H{"wallet_id": 1})
	if resp["created"] != false {
		t.Fatalf("二次创建应 created=false，实际 %v", resp["created"])
	}

	// 派生地址
	deriveBody := gin.H{"wallet_id": 1, "chain_type": "evm", "bip44_account": 0, "address_index": 0}
	rec, resp = call(t, engine, http.MethodPost, "/v1/wallets/derive-address", deriveBody)
	if rec.Code != 200 {
		t.Fatalf("派生应 200，实际 %d %v", rec.Code, resp)
	}
	address, _ := resp["address"].(string)
	if len(address) != 42 || address[:2] != "0x" {
		t.Fatalf("地址格式异常: %q", address)
	}
	// 同路径再次派生应得到相同地址（幂等登记）
	_, resp2 := call(t, engine, http.MethodPost, "/v1/wallets/derive-address", deriveBody)
	if resp2["address"] != address {
		t.Fatalf("同路径派生地址应稳定: %v != %v", resp2["address"], address)
	}

	// 用派生地址作为 from 签名（出账到外部地址）
	tx := gin.H{
		"chainId": 1, "nonce": 0, "from": address,
		"to":    "0x000000000000000000000000000000000000dEaD",
		"value": 1000000000000000, "data": "0x", "gas": 21000, "gasPrice": 20000000000,
	}
	rec, resp = call(t, engine, http.MethodPost, "/v1/sign/evm", gin.H{
		"wallet_id": 1, "chain_type": "evm", "bip44_account": 0, "address_index": 0, "tx_dict": tx,
	})
	if rec.Code != 200 {
		t.Fatalf("签名应 200，实际 %d %v", rec.Code, resp)
	}
	raw, _ := resp["raw_transaction"].(string)
	if len(raw) < 4 || raw[:2] != "0x" {
		t.Fatalf("raw_transaction 异常: %q", raw)
	}
}

func TestSignFromMismatch(t *testing.T) {
	engine := newMigratedServer(t).Router()
	call(t, engine, http.MethodPost, "/v1/wallets/create", gin.H{"wallet_id": 1})

	// from 故意填一个与派生路径不符的地址 → 1005
	tx := gin.H{
		"chainId": 1, "nonce": 0,
		"from":  "0x1111111111111111111111111111111111111111",
		"to":    "0x000000000000000000000000000000000000dEaD",
		"value": 1, "data": "0x", "gas": 21000, "gasPrice": 1,
	}
	rec, resp := call(t, engine, http.MethodPost, "/v1/sign/evm", gin.H{
		"wallet_id": 1, "chain_type": "evm", "bip44_account": 0, "address_index": 0, "tx_dict": tx,
	})
	if rec.Code != 403 || resp["code"] != "1005" {
		t.Fatalf("from 不匹配应 403/1005，实际 %d %v", rec.Code, resp)
	}
}

func TestSignMissingTxField(t *testing.T) {
	engine := newMigratedServer(t).Router()
	call(t, engine, http.MethodPost, "/v1/wallets/create", gin.H{"wallet_id": 1})

	// 缺 gasPrice
	tx := gin.H{"chainId": 1, "nonce": 0, "from": "0x1111111111111111111111111111111111111111",
		"to": "0x000000000000000000000000000000000000dEaD", "value": 1, "data": "0x", "gas": 21000}
	rec, resp := call(t, engine, http.MethodPost, "/v1/sign/evm", gin.H{
		"wallet_id": 1, "chain_type": "evm", "bip44_account": 0, "address_index": 0, "tx_dict": tx,
	})
	if rec.Code != 400 || resp["code"] != "1000" {
		t.Fatalf("缺字段应 400/1000，实际 %d %v", rec.Code, resp)
	}
}

func TestDeriveUnknownWallet(t *testing.T) {
	engine := newMigratedServer(t).Router()
	rec, resp := call(t, engine, http.MethodPost, "/v1/wallets/derive-address",
		gin.H{"wallet_id": 999, "chain_type": "evm", "bip44_account": 0, "address_index": 0})
	if rec.Code != 400 || resp["code"] != "1000" {
		t.Fatalf("未知钱包应 400/1000，实际 %d %v", rec.Code, resp)
	}
}

func TestAdminSummaryShape(t *testing.T) {
	engine := newMigratedServer(t).Router()
	call(t, engine, http.MethodPost, "/v1/wallets/create", gin.H{"wallet_id": 1})

	rec, resp := call(t, engine, http.MethodGet, "/internal/admin-summary", nil)
	if rec.Code != 200 {
		t.Fatalf("admin-summary 应 200，实际 %d %v", rec.Code, resp)
	}
	for _, key := range []string{"health", "wallets", "requests_last_hour", "recent_anomalies"} {
		if _, ok := resp[key]; !ok {
			t.Fatalf("admin-summary 缺字段 %q: %v", key, resp)
		}
	}
	wallets, _ := resp["wallets"].(map[string]any)
	if wallets["total"].(float64) != 1 {
		t.Fatalf("钱包总数应为 1，实际 %v", wallets["total"])
	}
}
