package throttle

import (
	"testing"
	"time"
)

func TestLimiterFixedWindow(t *testing.T) {
	l := NewLimiter(2, time.Minute)

	if !l.Allow("k") || !l.Allow("k") {
		t.Fatalf("前 2 次应放行")
	}
	if l.Allow("k") {
		t.Fatalf("第 3 次应超限")
	}
	// 不同 key 互不影响
	if !l.Allow("other") {
		t.Fatalf("不同 key 应独立计数")
	}
}

func TestLimiterWindowReset(t *testing.T) {
	l := NewLimiter(1, 30*time.Millisecond)
	if !l.Allow("k") {
		t.Fatalf("首次应放行")
	}
	if l.Allow("k") {
		t.Fatalf("窗口内第 2 次应超限")
	}
	time.Sleep(40 * time.Millisecond)
	if !l.Allow("k") {
		t.Fatalf("窗口过期后应重新放行")
	}
}

func TestReplayGuard(t *testing.T) {
	g := NewReplayGuard(time.Minute)
	if !g.CheckAndMark("req-1") {
		t.Fatalf("首次出现应返回 true")
	}
	if g.CheckAndMark("req-1") {
		t.Fatalf("重复 request_id 应判为重放（false）")
	}
	if !g.CheckAndMark("req-2") {
		t.Fatalf("不同 request_id 应独立")
	}
}

func TestReplayGuardExpiry(t *testing.T) {
	g := NewReplayGuard(30 * time.Millisecond)
	g.CheckAndMark("req")
	time.Sleep(40 * time.Millisecond)
	if !g.CheckAndMark("req") {
		t.Fatalf("TTL 过期后同一 id 应可再次接受")
	}
}
