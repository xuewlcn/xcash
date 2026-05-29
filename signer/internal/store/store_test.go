package store

import (
	"context"
	"database/sql"
	"errors"
	"path/filepath"
	"testing"

	_ "modernc.org/sqlite"
)

// newTestStore 用临时文件 SQLite 建一个迁移好的 Store。
func newTestStore(t *testing.T) *Store {
	t.Helper()
	path := filepath.Join(t.TempDir(), "test.sqlite")
	db, err := sql.Open("sqlite", path+"?_pragma=foreign_keys(ON)")
	if err != nil {
		t.Fatalf("open sqlite: %v", err)
	}
	db.SetMaxOpenConns(1)
	t.Cleanup(func() { db.Close() })

	st := New(db)
	if err := st.Migrate(context.Background()); err != nil {
		t.Fatalf("migrate: %v", err)
	}
	return st
}

func TestCreateWalletIfAbsentIsIdempotent(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()

	w1, created1, err := st.CreateWalletIfAbsent(ctx, 1001, "cipher-A")
	if err != nil || !created1 {
		t.Fatalf("首次创建应 created=true：created=%v err=%v", created1, err)
	}

	// 再次创建同一 wallet：应返回已存在，且绝不覆盖原密文。
	w2, created2, err := st.CreateWalletIfAbsent(ctx, 1001, "cipher-B-should-be-ignored")
	if err != nil {
		t.Fatalf("二次创建出错: %v", err)
	}
	if created2 {
		t.Fatalf("二次创建应 created=false")
	}
	if w2.EncryptedMnemonic != "cipher-A" {
		t.Fatalf("已有钱包密文被覆盖了：%q", w2.EncryptedMnemonic)
	}
	if w2.ID != w1.ID {
		t.Fatalf("二次返回的钱包不一致: %+v vs %+v", w2, w1)
	}
}

func TestGetWalletNotFound(t *testing.T) {
	st := newTestStore(t)
	if _, err := st.GetWallet(context.Background(), 9999); !errors.Is(err, ErrWalletNotFound) {
		t.Fatalf("应返回 ErrWalletNotFound，实际: %v", err)
	}
}

func TestRegisterDerivedAddressIdempotentAndDriftGuard(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	w, _, err := st.CreateWalletIfAbsent(ctx, 1, "cipher")
	if err != nil {
		t.Fatalf("create wallet: %v", err)
	}

	addr := "0x197A1bEE163923815Ba58EaD0F14B3Fcd8C5926d"
	// 同一派生身份重复登记同一地址：幂等，不报错。
	for i := 0; i < 2; i++ {
		if err := st.RegisterDerivedAddress(ctx, w.ID, "evm", 0, 0, addr); err != nil {
			t.Fatalf("第 %d 次登记应成功: %v", i+1, err)
		}
	}

	// 同一派生身份映射到不同地址：必须报漂移。
	err = st.RegisterDerivedAddress(ctx, w.ID, "evm", 0, 0, "0xDIFFERENT")
	if !errors.Is(err, ErrAddressDrift) {
		t.Fatalf("地址漂移应返回 ErrAddressDrift，实际: %v", err)
	}
}

func TestIsInternalAddressPerChain(t *testing.T) {
	st := newTestStore(t)
	ctx := context.Background()
	w, _, _ := st.CreateWalletIfAbsent(ctx, 1, "cipher")
	addr := "0x197A1bEE163923815Ba58EaD0F14B3Fcd8C5926d"
	if err := st.RegisterDerivedAddress(ctx, w.ID, "evm", 0, 0, addr); err != nil {
		t.Fatalf("register: %v", err)
	}

	cases := []struct {
		chain string
		addr  string
		want  bool
	}{
		{"evm", addr, true}, // 已登记
		{"evm", "0x0000000000000000000000000000000000000000", false}, // 未登记
		{"bitcoin", addr, false},                                     // 同地址不同链 → 不算内部
	}
	for _, c := range cases {
		got, err := st.IsInternalAddress(ctx, c.chain, c.addr)
		if err != nil {
			t.Fatalf("IsInternalAddress(%s,%s): %v", c.chain, c.addr, err)
		}
		if got != c.want {
			t.Fatalf("IsInternalAddress(%s,%s)=%v，期望 %v", c.chain, c.addr, got, c.want)
		}
	}
}
