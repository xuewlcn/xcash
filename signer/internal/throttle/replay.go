package throttle

import (
	"sync"
	"time"
)

// ReplayGuard 在 TTL 内记住已见过的 request_id，用于重放防护，
// 对齐原 Django 版 cache.add(request_id, ttl) 的“只接受一次”语义。
type ReplayGuard struct {
	mu   sync.Mutex
	ttl  time.Duration
	seen map[string]time.Time // request_id -> 过期时刻
}

// NewReplayGuard 构造重放防护，记录在 ttl 后过期。
func NewReplayGuard(ttl time.Duration) *ReplayGuard {
	g := &ReplayGuard{
		ttl:  ttl,
		seen: make(map[string]time.Time),
	}
	go g.janitor()
	return g
}

// CheckAndMark 原子地“检查并标记”：
// 首次出现返回 true（已记录）；TTL 内重复返回 false（判为重放）。
func (g *ReplayGuard) CheckAndMark(id string) bool {
	now := time.Now()
	g.mu.Lock()
	defer g.mu.Unlock()

	if expiry, ok := g.seen[id]; ok && now.Before(expiry) {
		return false
	}
	g.seen[id] = now.Add(g.ttl)
	return true
}

func (g *ReplayGuard) janitor() {
	ticker := time.NewTicker(g.ttl)
	defer ticker.Stop()
	for range ticker.C {
		now := time.Now()
		g.mu.Lock()
		for id, expiry := range g.seen {
			if now.After(expiry) {
				delete(g.seen, id)
			}
		}
		g.mu.Unlock()
	}
}
