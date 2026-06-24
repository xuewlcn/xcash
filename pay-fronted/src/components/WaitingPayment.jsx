import { Loader2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { useI18n } from "@/hooks/useI18n"

/**
 * 等待状态卡 - waiting 状态
 * 默认提示用户尽快付款；broadcasted 为 true 表示用户已通过钱包广播交易，
 * 文案切到「等待区块确认」，与支付卡片内「交易已提交」保持一致。
 */
function WaitingPayment({ broadcasted }) {
  const { t } = useI18n()

  return (
    <Card className="animate-in fade-in-0 slide-in-from-bottom-4 duration-500">
      <CardContent>
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-10 animate-spin text-muted-foreground" />

          <div className="text-center">
            <p className="font-medium">
              {t(broadcasted ? "waiting.broadcastTitle" : "waiting.title")}
            </p>
            <p className="text-sm text-muted-foreground mt-1">
              {t(broadcasted ? "waiting.broadcastDescription" : "waiting.description")}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default WaitingPayment
