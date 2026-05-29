// Package throttle 提供进程内的限流与重放防护，替代原 Django 版依赖的 Redis。
//
// signer 是单实例托管者，限流/重放本就是 DoS 与重放保护（非精确计费），
// 进程内实现足够；重启后计数清零可接受。
package throttle

import (
	"sync"
	"time"
)

// Limiter 是按 key 的固定窗口限流器，对齐原 Redis INCR+EXPIRE 语义。
type Limiter struct {
	mu      sync.Mutex
	window  time.Duration
	limit   int
	buckets map[string]*bucket
}

type bucket struct {
	count int
	start time.Time
}

// NewLimiter 构造限流器：每个 key 在 window 内最多 limit 次。
// 启动一个后台 janitor 定期清理过期窗口，避免 key 无限堆积。
func NewLimiter(limit int, window time.Duration) *Limiter {
	l := &Limiter{
		window:  window,
		limit:   limit,
		buckets: make(map[string]*bucket),
	}
	go l.janitor()
	return l
}

// Allow 记一次访问；仍在限额内返回 true，超限返回 false。
func (l *Limiter) Allow(key string) bool {
	now := time.Now()
	l.mu.Lock()
	defer l.mu.Unlock()

	b, ok := l.buckets[key]
	if !ok || now.Sub(b.start) >= l.window {
		// 新窗口
		l.buckets[key] = &bucket{count: 1, start: now}
		return l.limit >= 1
	}
	b.count++
	return b.count <= l.limit
}

func (l *Limiter) janitor() {
	ticker := time.NewTicker(l.window)
	defer ticker.Stop()
	for range ticker.C {
		now := time.Now()
		l.mu.Lock()
		for key, b := range l.buckets {
			if now.Sub(b.start) >= l.window {
				delete(l.buckets, key)
			}
		}
		l.mu.Unlock()
	}
}
