// Package httpapi 装配 signer 的 HTTP 层：路由、中间件与各端点 handler。
//
// 第 1 步（脚手架）只接入 /healthz；鉴权、限流、业务端点在后续步骤逐步加入。
package httpapi

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"xcash-signer/internal/config"
	"xcash-signer/internal/crypto"
	"xcash-signer/internal/store"
	"xcash-signer/internal/throttle"
)

// 限流与重放策略常量（对齐原 Django settings）。
const (
	rateLimitWindow  = time.Minute
	rateLimitMax     = 120 // IP 级：每分钟 120 次
	walletSignWindow = time.Minute
	walletSignMax    = 30 // 钱包签名级：每分钟 30 次
	replayTTL        = time.Minute
)

// Server 持有各 handler 共享的依赖（配置、存储层、助记词加解密、进程内限流/重放）。
// 用结构体方法做 handler，便于注入依赖、写测试，而不依赖全局变量。
type Server struct {
	cfg               config.Config
	st                *store.Store
	cipher            *crypto.Cipher
	ipLimiter         *throttle.Limiter
	walletSignLimiter *throttle.Limiter
	replay            *throttle.ReplayGuard
}

// New 构造 Server。
func New(cfg config.Config, st *store.Store) *Server {
	return &Server{
		cfg:               cfg,
		st:                st,
		cipher:            crypto.NewCipher(cfg.MnemonicEncKey),
		ipLimiter:         throttle.NewLimiter(rateLimitMax, rateLimitWindow),
		walletSignLimiter: throttle.NewLimiter(walletSignMax, walletSignWindow),
		replay:            throttle.NewReplayGuard(replayTTL),
	}
}

// Router 返回装配好的 gin 引擎。
func (s *Server) Router() *gin.Engine {
	if !s.cfg.Debug {
		gin.SetMode(gin.ReleaseMode)
	}
	// 用 New 而非 Default：不挂 gin 默认的 Logger，避免把请求体/敏感参数写进日志。
	r := gin.New()
	r.Use(gin.Recovery())

	// healthz 免鉴权、免限流、免审计。
	r.GET("/healthz", s.handleHealthz)

	// 受保护端点：审计（最外层，读 body + 落审计）→ 限流 → 鉴权。
	protected := r.Group("")
	protected.Use(s.auditMiddleware(), s.rateLimitMiddleware(), s.authMiddleware())
	protected.GET("/internal/admin-summary", s.handleAdminSummary)
	protected.POST("/v1/wallets/create", s.handleCreateWallet)
	protected.POST("/v1/wallets/derive-address", s.handleDeriveAddress)
	protected.POST("/v1/sign/evm", s.handleSignEVM)

	return r
}

// healthReport 与原 Django 版 _build_health_payload 对齐（去掉已移除的 cache 维度）。
type healthReport struct {
	Database       bool `json:"database"`
	AuthConfigured bool `json:"auth_configured"`
	Healthy        bool `json:"healthy"`
}

// checkHealth 探测各依赖，返回内部健康详情；对外 /healthz 只暴露 ok。
func (s *Server) checkHealth(c *gin.Context) healthReport {
	dbOK := s.st.Ping(c.Request.Context()) == nil
	authConfigured := s.cfg.SharedSecret != ""
	return healthReport{
		Database:       dbOK,
		AuthConfigured: authConfigured,
		Healthy:        dbOK && authConfigured,
	}
}

func (s *Server) handleHealthz(c *gin.Context) {
	// 对外仅暴露 ok/fail，不泄露数据库/密钥配置等基础设施状态。
	report := s.checkHealth(c)
	code := http.StatusOK
	if !report.Healthy {
		code = http.StatusServiceUnavailable
	}
	c.JSON(code, gin.H{"ok": report.Healthy})
}
