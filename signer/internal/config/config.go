// Package config 负责从环境变量加载 signer 运行配置。
//
// 设计与原 Django 版保持一致的安全约束：非 DEBUG 环境必须显式提供
// SIGNER_SHARED_SECRET 与 SIGNER_MNEMONIC_ENCRYPTION_KEY，缺失即拒绝启动，
// 避免用默认弱密钥跑生产。
package config

import (
	"fmt"
	"os"
	"strconv"
)

// Config 是 signer 的全部运行期配置。字段都来自环境变量（.env.signer）。
type Config struct {
	Debug          bool   // SIGNER_DEBUG：开发模式，跳过限流、放宽密钥校验
	SharedSecret   string // SIGNER_SHARED_SECRET：与主应用互信的 HMAC 密钥
	MnemonicEncKey string // SIGNER_MNEMONIC_ENCRYPTION_KEY：助记词加解密密钥
	DBPath         string // SIGNER_DB_PATH：SQLite 文件路径
	ListenAddr     string // SIGNER_LISTEN_ADDR：HTTP 监听地址
}

// 开发态默认占位密钥；与原 Django 版语义一致——生产若仍是这些值则拒绝启动。
const (
	devSharedSecretPlaceholder = ""
	devMnemonicKeyPlaceholder  = "dev-mnemonic-encryption-key-change-me"
	defaultDBPath              = "/data/signer.sqlite"
	defaultListenAddr          = ":8000"
)

// Load 读取环境变量并填充默认值，随后做安全校验。
// 校验不通过返回 error，由调用方决定是否终止启动。
func Load() (Config, error) {
	cfg := Config{
		Debug:          envBool("SIGNER_DEBUG", false),
		SharedSecret:   envStr("SIGNER_SHARED_SECRET", devSharedSecretPlaceholder),
		MnemonicEncKey: envStr("SIGNER_MNEMONIC_ENCRYPTION_KEY", devMnemonicKeyPlaceholder),
		DBPath:         envStr("SIGNER_DB_PATH", defaultDBPath),
		ListenAddr:     envStr("SIGNER_LISTEN_ADDR", defaultListenAddr),
	}

	if err := cfg.validate(); err != nil {
		return Config{}, err
	}
	return cfg, nil
}

// validate 复刻原 Django 版的生产安全门槛。
func (c Config) validate() error {
	if c.Debug {
		return nil
	}
	if c.SharedSecret == "" {
		return fmt.Errorf("非开发环境必须显式配置 SIGNER_SHARED_SECRET")
	}
	if c.MnemonicEncKey == "" || c.MnemonicEncKey == devMnemonicKeyPlaceholder {
		return fmt.Errorf("非开发环境必须显式配置 SIGNER_MNEMONIC_ENCRYPTION_KEY")
	}
	return nil
}

func envStr(key, def string) string {
	if v, ok := os.LookupEnv(key); ok && v != "" {
		return v
	}
	return def
}

func envBool(key string, def bool) bool {
	v, ok := os.LookupEnv(key)
	if !ok || v == "" {
		return def
	}
	b, err := strconv.ParseBool(v)
	if err != nil {
		return def
	}
	return b
}
