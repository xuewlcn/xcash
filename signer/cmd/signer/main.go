// Command signer 是 xcash 的独立签名服务（Go 重写版）。
//
// 它持有热钱包助记词，对外只提供地址派生与交易签名。存储用 SQLite，
// 不依赖 Postgres 或 Redis，终态是「一个二进制 + 一个 .sqlite 文件」。
package main

import (
	"context"
	"database/sql"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	_ "modernc.org/sqlite" // 注册纯 Go 的 "sqlite" database/sql 驱动

	"xcash-signer/internal/config"
	"xcash-signer/internal/httpapi"
	"xcash-signer/internal/store"
)

func main() {
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("配置加载失败: %v", err)
	}

	db, err := openDB(cfg.DBPath)
	if err != nil {
		log.Fatalf("打开 SQLite 失败 (%s): %v", cfg.DBPath, err)
	}
	defer db.Close()

	st := store.New(db)
	if err := st.Migrate(context.Background()); err != nil {
		log.Fatalf("应用 schema 失败: %v", err)
	}

	srv := &http.Server{
		Addr:              cfg.ListenAddr,
		Handler:           httpapi.New(cfg, st).Router(),
		ReadHeaderTimeout: 5 * time.Second,
	}

	// 优雅停机：收到 SIGINT/SIGTERM 后停止接收新请求并在超时内排空。
	go func() {
		log.Printf("signer 监听 %s (debug=%v, db=%s)", cfg.ListenAddr, cfg.Debug, cfg.DBPath)
		if err := srv.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("HTTP 服务异常退出: %v", err)
		}
	}()

	stop := make(chan os.Signal, 1)
	signal.Notify(stop, syscall.SIGINT, syscall.SIGTERM)
	<-stop

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := srv.Shutdown(ctx); err != nil {
		log.Printf("停机超时: %v", err)
	}
	log.Println("signer 已退出")
}

// openDB 打开 SQLite 并设置适合单实例托管者的 PRAGMA：
// WAL 提升并发读、busy_timeout 避免偶发写锁直接报错、foreign_keys 启用外键约束。
func openDB(path string) (*sql.DB, error) {
	dsn := path + "?_pragma=journal_mode(WAL)&_pragma=busy_timeout(5000)&_pragma=foreign_keys(ON)"
	db, err := sql.Open("sqlite", dsn)
	if err != nil {
		return nil, err
	}
	// SQLite 单写者：限制为单连接可避免 "database is locked" 的写写竞争。
	db.SetMaxOpenConns(1)
	if err := db.Ping(); err != nil {
		db.Close()
		return nil, err
	}
	return db, nil
}
