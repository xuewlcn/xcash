import { Loader2 } from "lucide-react"
import { Card, CardContent } from "@/components/ui/card"
import { useI18n } from "@/hooks/useI18n"

/**
 * 等待支付组件 - waiting 状态
 * 用户还未付款,显示等待提示
 */
function WaitingPayment() {
  const { t } = useI18n()

  return (
    <Card className="animate-in fade-in-0 slide-in-from-bottom-4 duration-500">
      <CardContent>
        <div className="flex flex-col items-center gap-4">
          <Loader2 className="size-10 animate-spin text-muted-foreground" />

          <div className="text-center">
            <p className="font-medium">{t("waiting.title")}</p>
            <p className="text-sm text-muted-foreground mt-1">{t("waiting.description")}</p>
          </div>
        </div>
      </CardContent>
    </Card>
  )
}

export default WaitingPayment
