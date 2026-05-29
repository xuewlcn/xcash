package httpapi

import "github.com/gin-gonic/gin"

// apiError 是对外错误，序列化为 {code, message, detail}，与原 Django 版错误域一致。
type apiError struct {
	code    string
	message string
	status  int
}

// signer 实际会返回的最小错误码集合（与 SPEC / 原 Django 版逐一对应）。
var (
	errParameter  = apiError{code: "1000", message: "参数错误", status: 400}
	errSignature  = apiError{code: "1003", message: "签名错误", status: 403}
	errAccessDeny = apiError{code: "1005", message: "无访问权限", status: 403}
	errReplay     = apiError{code: "1009", message: "请求重复", status: 400}
	errRateLimit  = apiError{code: "1010", message: "请求过于频繁", status: 429}
	// errRequestTooLarge 在鉴权前拦截超大请求体，防止内存耗尽 DoS。客户端对任何非 2xx
	// 都按失败处理，故新增该码不破坏 drop-in 契约。
	errRequestTooLarge = apiError{code: "1011", message: "请求体过大", status: 413}
)

// errInternal 用于派生/数据库等内部故障（原 Django 版会 500）。不在主应用客户端的
// 错误依赖范围内，客户端对任何非 2xx 都按失败处理。
var errInternal = apiError{code: "5000", message: "内部错误", status: 500}

// abortError 终止请求并返回标准错误体，同时把错误码写入上下文供审计中间件读取。detail 可空。
func abortError(c *gin.Context, e apiError, detail string) {
	c.Set(ctxKeyErrorCode, e.code)
	c.AbortWithStatusJSON(e.status, gin.H{
		"code":    e.code,
		"message": e.message,
		"detail":  detail,
	})
}
