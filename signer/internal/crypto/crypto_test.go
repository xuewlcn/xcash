package crypto

import (
	"strings"
	"testing"
)

func TestGenerateAndNormalizeMnemonic(t *testing.T) {
	m, err := GenerateMnemonic()
	if err != nil {
		t.Fatalf("生成助记词失败: %v", err)
	}
	// 24 词
	if got := len(strings.Fields(m)); got != 24 {
		t.Fatalf("应为 24 词，实际 %d", got)
	}
	if _, err := NormalizeMnemonic(m); err != nil {
		t.Fatalf("生成的助记词应通过校验: %v", err)
	}
	// 折叠多余空白后仍有效
	if _, err := NormalizeMnemonic("  " + m + "   "); err != nil {
		t.Fatalf("折叠空白后应有效: %v", err)
	}
	// 非法助记词被拒
	if _, err := NormalizeMnemonic("not a valid mnemonic phrase"); err == nil {
		t.Fatalf("非法助记词应被拒绝")
	}
}

func TestCipherRoundTrip(t *testing.T) {
	c := NewCipher("a-high-entropy-32B-or-more-secret-key-xxxxxxxx")
	plain := "abandon abandon abandon ... agent"

	token, err := c.Encrypt(plain)
	if err != nil {
		t.Fatalf("加密失败: %v", err)
	}
	got, err := c.Decrypt(token)
	if err != nil {
		t.Fatalf("解密失败: %v", err)
	}
	if got != plain {
		t.Fatalf("往返不一致: %q != %q", got, plain)
	}

	// 同一明文两次加密应产生不同密文（盐 + nonce 随机）
	token2, _ := c.Encrypt(plain)
	if token == token2 {
		t.Fatalf("两次加密密文相同，盐/nonce 未随机")
	}

	// 错误密钥无法解密（GCM 认证失败）
	wrong := NewCipher("a-different-key-zzzzzzzzzzzzzzzzzzzzzzzzzzzzzz")
	if _, err := wrong.Decrypt(token); err == nil {
		t.Fatalf("错误密钥应解密失败")
	}
}
