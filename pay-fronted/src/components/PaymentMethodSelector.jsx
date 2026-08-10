import { Check, Loader2, AlertCircle } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Alert, AlertDescription } from "@/components/ui/alert"
import { cn } from "@/lib/utils"
import TokenSelector from "@/components/TokenSelector"
import ChainSelector from "@/components/ChainSelector"
import { useI18n } from "@/hooks/useI18n"

// 小节标题：序号圆点（已选 → 品牌色 + 勾，未选 → 描边数字）
function SectionHeading({ done, number, title, desc, trailing, dimmed }) {
  return (
    <div className={cn("flex items-start gap-3", dimmed && "opacity-50")}>
      <div
        className={cn(
          "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full transition-colors",
          done
            ? "bg-primary text-primary-foreground"
            : "border bg-card text-[11px] font-bold text-muted-foreground"
        )}
      >
        {done ? <Check className="size-3.5" /> : number}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-semibold tracking-tight">{title}</span>
          {trailing}
        </div>
        <p className="mt-0.5 text-xs text-muted-foreground">{desc}</p>
      </div>
    </div>
  )
}

function PaymentMethodSelector({
  availableMethods,
  selectedCrypto,
  selectedChain,
  onCryptoChange,
  onChainChange,
  isSelecting,
  isEditing,
  error,
  onCancelEdit,
}) {
  const { t } = useI18n()

  return (
    <div className="flex flex-col gap-6">
      {/* 页头 */}
      <div className="space-y-1.5">
        <h1 className="text-xl font-bold tracking-tight">{t("payment.selectMethod")}</h1>
        <p className="text-sm text-muted-foreground">{t("payment.selectMethodDesc")}</p>
      </div>

      {/* Step 1: Token */}
      <section className="flex flex-col gap-3.5">
        <SectionHeading
          done={Boolean(selectedCrypto)}
          number={1}
          title={t("payment.selectToken")}
          desc={t("payment.selectTokenDesc")}
          trailing={
            selectedCrypto && (
              <span className="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-brand">
                {selectedCrypto}
              </span>
            )
          }
        />
        <TokenSelector
          availableMethods={availableMethods}
          selectedCrypto={selectedCrypto}
          onCryptoChange={onCryptoChange}
          disabled={isSelecting}
        />
      </section>

      {/* Step 2: Network */}
      <section className="flex flex-col gap-3.5">
        <SectionHeading
          done={Boolean(selectedChain)}
          number={2}
          title={t("payment.selectNetwork")}
          desc={t("payment.selectNetworkDesc")}
          dimmed={!selectedCrypto && !selectedChain}
          trailing={
            selectedChain && (
              <span className="rounded-full bg-brand-soft px-2.5 py-0.5 text-xs font-semibold text-brand">
                {selectedChain}
              </span>
            )
          }
        />
        <ChainSelector
          availableMethods={availableMethods}
          selectedCrypto={selectedCrypto}
          selectedChain={selectedChain}
          onChainChange={onChainChange}
          disabled={isSelecting}
        />
      </section>

      {/* Loading */}
      {isSelecting && (
        <div className="flex items-center justify-center gap-2.5 rounded-xl border bg-card py-4">
          <Loader2 className="size-4 animate-spin text-primary" />
          <p className="text-sm text-muted-foreground">{t("payment.gettingPaymentInfo")}</p>
        </div>
      )}

      {/* Error */}
      {error && !isSelecting && (
        <Alert variant="destructive">
          <AlertCircle />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Cancel edit */}
      {isEditing && !isSelecting && (
        <div className="flex justify-end">
          <Button variant="ghost" onClick={onCancelEdit} size="sm">
            {t("common.cancel")}
          </Button>
        </div>
      )}
    </div>
  )
}

export default PaymentMethodSelector
