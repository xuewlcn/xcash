// src/components/StepCompleted.jsx
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Check } from "lucide-react"
import { useI18n } from "@/hooks/useI18n"

function StepCompleted({ invoice }) {
  const { t } = useI18n()

  const confirmingProgress = invoice?.payment?.confirm_progress || {}
  const progress = confirmingProgress.progress || 0
  const hasConfirmedCount = confirmingProgress.has_confirmed_count || 0
  const needConfirmedCount = confirmingProgress.need_confirmed_count || 0
  const invoiceAmount = [invoice?.amount, invoice?.currency].filter(Boolean).join(" ")
  const invoiceRows = [
    invoice?.title && { label: t("invoice.subject"), value: invoice.title },
    invoice?.out_no && { label: t("invoice.orderNumber"), value: invoice.out_no, mono: true },
    invoice?.sys_no && { label: t("invoice.systemNumber"), value: invoice.sys_no, mono: true },
    invoiceAmount && { label: t("invoice.amountDue"), value: invoiceAmount },
  ].filter(Boolean)

  return (
    <div className="animate-in fade-in-0 slide-in-from-bottom-2 duration-300">
      <div className="glow-card overflow-hidden rounded-2xl border bg-card shadow-md">
        <div className="flex flex-col gap-6 px-6 py-10">
          {/* Success hero */}
          <div className="flex flex-col items-center gap-4 text-center">
            <div className="relative flex size-20 items-center justify-center">
              <span className="absolute inset-0 animate-pulse-ring rounded-full bg-success/30" />
              <span className="absolute inset-0 rounded-full bg-success-soft ring-1 ring-success-border" />
              <span className="relative flex size-12 items-center justify-center rounded-full bg-success text-success-foreground shadow-[0_0_24px_#72e85773] animate-in zoom-in-50 duration-500">
                <Check className="size-6" strokeWidth={3} />
              </span>
            </div>
            <div>
              <h2 className="text-xl font-bold tracking-tight">
                {t("payment.paymentCompleted") || "支付成功！"}
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                {t("confirmation.transactionConfirmed") || "区块链交易已确认"}
              </p>
            </div>
          </div>

          {/* Amount summary */}
          <div className="flex items-center justify-between rounded-xl border bg-muted/40 p-4">
            <div>
              <div className="mb-1 text-xs text-muted-foreground">{t("invoice.amountDue") || "实付金额"}</div>
              <div className="font-mono text-lg font-bold tabular-nums">
                {invoice?.pay_amount} {invoice?.crypto}
              </div>
            </div>
            <div className="text-right">
              <div className="mb-1 text-xs text-muted-foreground">{invoice?.currency}</div>
              <div className="text-lg font-bold tabular-nums">{invoice?.amount}</div>
            </div>
          </div>

          {/* Basic invoice info */}
          {invoiceRows.length > 0 && (
            <div className="rounded-xl border p-4">
              <div className="mb-3 text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("invoice.basicInfo")}
              </div>
              <dl className="grid gap-3">
                {invoiceRows.map((row) => (
                  <div key={row.label} className="grid min-h-5 grid-cols-[5rem_minmax(0,1fr)] items-center gap-3">
                    <dt className="text-xs font-medium leading-5 text-muted-foreground">{row.label}</dt>
                    <dd className={row.mono
                      ? "break-all text-right font-mono text-xs leading-5"
                      : "break-words text-right text-xs font-medium leading-5"}
                    >
                      {row.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}

          {/* Block confirmation progress */}
          <div className="flex flex-col gap-2 rounded-xl border border-success-border bg-success-soft p-4">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium">
                {t("confirmation.blockConfirmation") || "区块确认"}
              </span>
              <span className="font-mono text-sm font-bold tabular-nums text-success">
                {progress}%
              </span>
            </div>
            <Progress
              value={progress}
              className="bg-[#e4e9ee] dark:bg-[#26313d]"
              indicatorClassName="bg-gradient-to-r from-[#3dcf40] to-[#72e857] shadow-[0_0_10px_#72e85780]"
            />
            <div className="flex justify-between text-xs text-muted-foreground">
              <span>{t("confirmation.confirmed") || "已确认"} {hasConfirmedCount} {t("confirmation.blocks") || "区块"}</span>
              <span>{t("confirmation.needs") || "需要"} {needConfirmedCount} {t("confirmation.blocks") || "区块"}</span>
            </div>
          </div>

          {/* Transaction hash */}
          {invoice?.payment?.hash && (
            <div className="flex flex-col gap-2">
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                {t("payment.transactionHash") || "交易哈希"}
              </span>
              <code className="block break-all rounded-xl bg-muted p-3.5 font-mono text-xs leading-relaxed text-muted-foreground">
                {invoice.payment.hash}
              </code>
            </div>
          )}

          {/* Return to merchant */}
          {invoice?.return_url && (
            <Button onClick={() => window.open(invoice.return_url, "_blank")} className="w-full">
              {t("payment.returnToMerchant") || "返回商户"}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

export default StepCompleted
