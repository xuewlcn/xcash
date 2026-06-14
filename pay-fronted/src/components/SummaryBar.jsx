// src/components/SummaryBar.jsx
import { Moon, Sun } from "lucide-react"
import LogoMark from "@/components/LogoMark"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { useI18n } from "@/hooks/useI18n"
import { getInvoiceDisplayStatus } from "@/lib/invoiceStatus"

// 状态 → Badge 语义变体。只改变用户可见状态色，不影响后端状态值。
const STATUS_VARIANT = {
  waiting: "info",
  confirming: "info",
  finalizing: "info",
  completed: "success",
  expired: "destructive",
}

// 进行中的状态展示一个脉冲点（继承 badge 文字色，非自定义颜色）。
const PULSING = new Set(["waiting", "confirming", "finalizing"])

function SummaryBar({ invoice, isDark, toggleTheme }) {
  const { t, locale, setLocale } = useI18n()
  const toggleLocale = () => setLocale(locale === "zh" ? "en" : "zh")

  const hasPayMethod = Boolean(invoice?.crypto && invoice?.pay_amount)
  const displayStatus = getInvoiceDisplayStatus(invoice)
  const variant = STATUS_VARIANT[displayStatus] ?? "outline"

  return (
    <div className="border-b px-5 py-3">
      <div className="max-w-lg mx-auto flex items-center justify-between gap-3">
        {/* Brand */}
        <div className="flex items-center gap-2 shrink-0">
          <LogoMark size={20} />
          <span className="font-semibold text-sm tracking-tight">Xcash</span>
        </div>

        {/* Amount */}
        <div className="text-center flex-1 min-w-0">
          <div className="flex items-baseline justify-center gap-2 flex-wrap">
            <span className="text-lg font-semibold tabular-nums sm:text-xl">
              {invoice?.amount} {invoice?.currency}
            </span>
            {hasPayMethod && (
              <span className="text-xs font-mono text-muted-foreground tabular-nums">
                ≈ {invoice.pay_amount} {invoice.crypto}
              </span>
            )}
          </div>
          {invoice?.title && (
            <div className="text-xs text-muted-foreground truncate mt-0.5">{invoice.title}</div>
          )}
        </div>

        {/* Status */}
        <Badge variant={variant} className="shrink-0">
          {PULSING.has(displayStatus) && (
            <span className="size-1.5 rounded-full bg-current animate-pulse" />
          )}
          {t(`invoice.status.${displayStatus}`) || displayStatus}
        </Badge>

        {/* Locale toggle */}
        <Button
          variant="outline"
          size="icon"
          onClick={toggleLocale}
          className="shrink-0 text-xs font-semibold"
          aria-label="Switch language"
          title={locale === "zh" ? "Switch to English" : "切换到中文"}
        >
          {locale === "zh" ? "EN" : "中"}
        </Button>

        {/* Theme toggle */}
        <Button
          variant="outline"
          size="icon"
          onClick={toggleTheme}
          className="shrink-0"
          aria-label="Toggle theme"
        >
          {isDark ? <Sun /> : <Moon />}
        </Button>
      </div>
    </div>
  )
}

export default SummaryBar
