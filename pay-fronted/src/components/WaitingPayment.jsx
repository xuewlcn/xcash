import { useI18n } from "@/hooks/useI18n"

/**
 * 等待状态条 - waiting 状态
 * waffo 式蓝色信息盒：蓝色是辅助提示色，与品牌绿主行动色区分。
 * broadcasted 为 true 表示用户已通过钱包广播交易，
 * 文案切到「等待区块确认」，与支付卡片内「交易已提交」保持一致。
 */
function WaitingPayment({ broadcasted }) {
  const { t } = useI18n()

  return (
    <div className="flex items-center gap-3.5 rounded-xl border border-info-border bg-info-soft px-5 py-4 animate-in fade-in-0 slide-in-from-bottom-4 duration-500">
      {/* 雷达脉冲 */}
      <span className="relative flex size-2.5 shrink-0">
        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-info opacity-60" />
        <span className="relative inline-flex size-2.5 rounded-full bg-info shadow-[0_0_8px_#7cb8ff99]" />
      </span>
      <div className="min-w-0">
        <p className="text-sm font-medium text-info">
          {t(broadcasted ? "waiting.broadcastTitle" : "waiting.title")}
        </p>
        <p className="mt-0.5 text-xs text-muted-foreground">
          {t(broadcasted ? "waiting.broadcastDescription" : "waiting.description")}
        </p>
      </div>
    </div>
  )
}

export default WaitingPayment
