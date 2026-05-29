package crypto

import (
	"crypto/aes"
	"crypto/cipher"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"errors"
	"io"

	"golang.org/x/crypto/hkdf"
)

// 助记词对称加密：AES-256-GCM。
//
// 密钥派生用 HKDF-SHA256 而非 PBKDF2/scrypt：signer 的加密密钥来自
// SIGNER_MNEMONIC_ENCRYPTION_KEY，由 init_env 生成为 64 字符高熵随机串
// （config 在生产环境拒绝弱默认值），输入本就高熵，HKDF 是正确且快速的选择，
// 无需慢哈希抗暴力。每条密文用独立随机盐派生子密钥 + 独立随机 nonce。
//
// 存储格式：base64( salt[16] || nonce[12] || ciphertext+tag )。
const (
	cipherSaltLen  = 16
	cipherNonceLen = 12 // AES-GCM 标准 nonce 长度
	cipherKeyLen   = 32 // AES-256
)

var cipherHKDFInfo = []byte("xcash-signer-mnemonic-v1")

// Cipher 持有主密钥（来自配置），提供助记词加解密。
type Cipher struct {
	masterKey []byte
}

// NewCipher 用配置中的加密密钥构造 Cipher。
func NewCipher(key string) *Cipher {
	return &Cipher{masterKey: []byte(key)}
}

// deriveKey 用 HKDF-SHA256 从主密钥 + 盐派生 32 字节 AES 密钥。
func (c *Cipher) deriveKey(salt []byte) ([]byte, error) {
	r := hkdf.New(sha256.New, c.masterKey, salt, cipherHKDFInfo)
	key := make([]byte, cipherKeyLen)
	if _, err := io.ReadFull(r, key); err != nil {
		return nil, err
	}
	return key, nil
}

// Encrypt 加密明文，返回 base64(salt+nonce+ciphertext)。
func (c *Cipher) Encrypt(plaintext string) (string, error) {
	salt := make([]byte, cipherSaltLen)
	if _, err := rand.Read(salt); err != nil {
		return "", err
	}
	key, err := c.deriveKey(salt)
	if err != nil {
		return "", err
	}
	gcm, err := newGCM(key)
	if err != nil {
		return "", err
	}
	nonce := make([]byte, cipherNonceLen)
	if _, err := rand.Read(nonce); err != nil {
		return "", err
	}
	ciphertext := gcm.Seal(nil, nonce, []byte(plaintext), nil)

	out := make([]byte, 0, len(salt)+len(nonce)+len(ciphertext))
	out = append(out, salt...)
	out = append(out, nonce...)
	out = append(out, ciphertext...)
	return base64.StdEncoding.EncodeToString(out), nil
}

// Decrypt 解密 Encrypt 产出的密文。
func (c *Cipher) Decrypt(token string) (string, error) {
	raw, err := base64.StdEncoding.DecodeString(token)
	if err != nil {
		return "", err
	}
	if len(raw) < cipherSaltLen+cipherNonceLen {
		return "", errors.New("密文长度非法")
	}
	salt := raw[:cipherSaltLen]
	nonce := raw[cipherSaltLen : cipherSaltLen+cipherNonceLen]
	ciphertext := raw[cipherSaltLen+cipherNonceLen:]

	key, err := c.deriveKey(salt)
	if err != nil {
		return "", err
	}
	gcm, err := newGCM(key)
	if err != nil {
		return "", err
	}
	plaintext, err := gcm.Open(nil, nonce, ciphertext, nil)
	if err != nil {
		return "", err
	}
	return string(plaintext), nil
}

func newGCM(key []byte) (cipher.AEAD, error) {
	block, err := aes.NewCipher(key)
	if err != nil {
		return nil, err
	}
	return cipher.NewGCM(block)
}
