import { useEffect, useState } from "react"
import QRCode from "qrcode"
import { Copy, Check, Clock, CheckCircle2, ArrowLeft, Loader2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { useMetadataContext } from "@/context/MetadataContext"
import { getConfirmationProgress, isPaymentConfirming } from "@/lib/invoiceStatus"
import { useI18n } from "@/hooks/useI18n"
import { cn } from "@/lib/utils"
import WalletPay from "@/components/WalletPay"
import TronWalletPay from "@/components/TronWalletPay"

// 复制按钮：copied 命中当前字段时切换为对勾。提到组件外，避免在 render 期间创建组件。
function CopyButton({ copied, onCopy, className }) {
  return (
    <button
      type="button"
      onClick={onCopy}
      aria-label="Copy"
      className={cn(
        "flex size-7 shrink-0 items-center justify-center rounded-lg border bg-card text-muted-foreground transition-colors hover:border-brand/40 hover:text-brand focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        copied && "border-success/40 text-success hover:text-success",
        className
      )}
    >
      {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
    </button>
  )
}

// waffo 式字段盒：标签行（左标签 + 右动作）+ 内容区，承载地址/金额/哈希等可复制字段
function FieldBox({ label, action, children, className }) {
  return (
    <div className={cn("rounded-xl border bg-muted/30 px-4 py-3.5", className)}>
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-medium text-muted-foreground">{label}</span>
        {action}
      </div>
      <div className="mt-2">{children}</div>
    </div>
  )
}

function PaymentAddress({ invoice, onReset, onBroadcast }) {
  const { t } = useI18n()
  const { getChain, getCrypto } = useMetadataContext()
  const [qrCodeUrl, setQrCodeUrl] = useState("")
  const [copiedField, setCopiedField] = useState("")

  const hasPayment = Boolean(invoice?.payment)
  const isConfirming = isPaymentConfirming(invoice)
  const isCompleted = invoice?.status === "completed"
  const confirmingProgress = getConfirmationProgress(invoice)
  const progress = confirmingProgress.progress || 0
  const hasConfirmedCount = confirmingProgress.has_confirmed_count || 0
  const needConfirmedCount = confirmingProgress.need_confirmed_count || 0
  // 区块层已达到目标确认数（按链高度即时判定，与后端 transfer.status 解耦）。
  // 后端 invoice.status 切到 completed 还要 worker 跑 RPC 二次校验，存在时延，
  // 这段窗口内把标题/描述切到「最终化中」，让用户知道在等什么，避免误以为卡住。
  const isFinalizing = isConfirming && progress >= 100

  useEffect(() => {
    if (!invoice?.pay_address) {
      return
    }

    // EVM 账单优先用 EIP-681 URI（含链/加密货币/金额），扫码即预填，
    // 大幅减少手输金额导致的「付款金额不符」；无 URI（如 Tron）时退回纯地址。
    const qrValue = invoice.payment_uri || invoice.pay_address

    // 二维码需固定深/浅对比才能被钱包扫描，这里使用静态黑白（功能性需求，非主题色）。
    QRCode.toDataURL(qrValue, {
      width: 320,
      margin: 0,
      color: { dark: "#000000", light: "#ffffff" },
    })
      .then(setQrCodeUrl)
      .catch((err) => {
        console.error("QR code generation failed:", err)
      })
  }, [invoice?.payment_uri, invoice?.pay_address])

  if (!invoice?.pay_address) {
    return null
  }

  const cryptoMeta = getCrypto(invoice.crypto)
  const chainMeta = getChain(invoice.chain)

  const handleCopy = (value, field) => {
    navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopiedField(field)
        setTimeout(() => setCopiedField(""), 2000)
      })
      .catch((err) => {
        console.error("Copy failed:", err)
      })
  }

  const headerTitle = isCompleted
    ? t("payment.paymentCompleted")
    : isFinalizing
      ? t("payment.paymentFinalizing")
      : isConfirming
        ? t("payment.paymentConfirming")
        : t("payment.paymentInfo")

  return (
    <div className="glow-card overflow-hidden rounded-2xl border bg-card shadow-md">
      {/* 头部：waffo 式着色横幅 —— 图标方块 + 标题/副标题 + 右侧网络胶囊 */}
      <div className="flex items-center gap-3.5 border-b bg-gradient-to-br from-[#0a934d17] via-transparent to-transparent px-6 py-5 dark:from-[#72e85712]">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-brand-soft ring-1 ring-brand-border">
          <img
            src={cryptoMeta.icon || undefined}
            alt=""
            className="size-6 rounded-full"
            onError={(e) => { e.target.style.visibility = "hidden" }}
          />
        </span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold tracking-tight">{headerTitle}</h2>
          <div className="mt-0.5 text-sm text-muted-foreground">
            {isCompleted ? (
              <span className="flex items-center gap-1.5 text-success">
                <CheckCircle2 className="size-3.5" />
                {t("confirmation.transactionConfirmed")}
              </span>
            ) : isFinalizing ? (
              <span className="flex items-center gap-1.5">
                <Clock className="size-3.5" />
                {t("confirmation.awaitingFinalization")}
              </span>
            ) : isConfirming ? (
              <span className="flex items-center gap-1.5">
                <Clock className="size-3.5" />
                {t("confirmation.waitingConfirmation")}
              </span>
            ) : (
              <span>
                {t("payment.transferInstruction", {
                  amount: invoice.pay_amount,
                  crypto: invoice.crypto,
                })}
              </span>
            )}
          </div>
        </div>
        <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-brand-border bg-brand-soft px-2.5 py-1 text-xs font-medium text-brand">
          <img
            src={chainMeta.icon || undefined}
            alt=""
            className="size-3.5 rounded-full"
            onError={(e) => { e.target.style.visibility = "hidden" }}
          />
          {chainMeta.name}
          {chainMeta.isTestnet && ` · ${t("selector.testNetwork")}`}
        </span>
      </div>

      <div className="flex flex-col gap-4 px-6 py-6">
        {/* Confirmation progress */}
        {hasPayment && (isConfirming || isCompleted) && (
          <>
            <div className="relative overflow-hidden rounded-xl border border-success-border bg-success-soft p-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-muted-foreground">
                  {t("confirmation.blockConfirmation")}
                </span>
                <span className="font-mono text-sm font-bold tabular-nums text-success">
                  {progress}%
                </span>
              </div>
              <div className="mt-2.5">
                <Progress
                  value={progress}
                  className="bg-[#e4e9ee] dark:bg-[#26313d]"
                  indicatorClassName="bg-gradient-to-r from-[#3dcf40] to-[#72e857] shadow-[0_0_10px_#72e85780]"
                />
              </div>
              <div className="mt-2.5 flex items-center justify-between text-xs text-muted-foreground">
                <span>{t("confirmation.confirmed")} {hasConfirmedCount} {t("confirmation.blocks")}</span>
                <span>{t("confirmation.needs")} {needConfirmedCount} {t("confirmation.blocks")}</span>
              </div>
              {isConfirming && !isFinalizing && (
                <div className="pointer-events-none absolute inset-y-0 left-0 w-1/3 animate-shimmer bg-gradient-to-r from-transparent via-white/25 to-transparent" />
              )}
            </div>

            {/* Transaction hash */}
            {invoice.payment.hash && (
              <FieldBox label={t("payment.transactionHash")}>
                <code className="block break-all font-mono text-[13px] leading-relaxed text-muted-foreground">
                  {invoice.payment.hash}
                </code>
              </FieldBox>
            )}
          </>
        )}

        {/* QR — only when not yet paid */}
        {!hasPayment && (
          <div className="flex flex-col items-center gap-2.5 py-2">
            <div className="rounded-2xl border bg-white p-3.5 shadow-sm ring-1 ring-black/5 dark:shadow-[0_0_28px_#72e8572e] dark:ring-[#72e85740]">
              {qrCodeUrl ? (
                <img src={qrCodeUrl} alt={t("payment.scanQRCode")} className="size-44" />
              ) : (
                <div className="flex size-44 items-center justify-center">
                  <Loader2 className="size-6 animate-spin text-muted-foreground" />
                </div>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{t("payment.scanQRCode")}</p>
          </div>
        )}

        {/* Amount field */}
        <FieldBox
          label={t("payment.paymentAmount")}
          action={
            <CopyButton
              copied={copiedField === "amount"}
              onCopy={() => handleCopy(invoice.pay_amount, "amount")}
            />
          }
        >
          <div className="flex items-center gap-2.5">
            <img
              src={cryptoMeta.icon || undefined}
              alt=""
              className="size-7 shrink-0 rounded-full"
              onError={(e) => { e.target.style.visibility = "hidden" }}
            />
            <span className="truncate font-mono text-xl font-bold tabular-nums tracking-tight">
              {invoice.pay_amount}
            </span>
            <span className="shrink-0 rounded-full bg-brand-soft px-2 py-0.5 text-xs font-semibold text-brand">
              {invoice.crypto}
            </span>
          </div>
        </FieldBox>

        {/* Payment address field */}
        <FieldBox
          label={t("payment.paymentAddress")}
          action={
            <CopyButton
              copied={copiedField === "address"}
              onCopy={() => handleCopy(invoice.pay_address, "address")}
            />
          }
        >
          <code className="block break-all font-mono text-[13px] leading-relaxed">
            {invoice.pay_address}
          </code>
        </FieldBox>

        {/* Contract address */}
        {invoice.crypto_address && (
          <FieldBox label={`${invoice.crypto} ${t("payment.contractAddress")}`} className="bg-muted/20">
            <code className="block select-none break-all font-mono text-xs leading-relaxed text-muted-foreground">
              {invoice.crypto_address.slice(0, 6)}...{invoice.crypto_address.slice(-8)}
            </code>
          </FieldBox>
        )}

        {/* Wallet pay (注入式 EVM 钱包) — 作为「手动转账」之外的备选项放在底部；
            组件在未检测到钱包时自渲染为 null，二维码与地址始终保留作主路径 */}
        {!hasPayment && <WalletPay invoice={invoice} onBroadcast={onBroadcast} />}
        {!hasPayment && <TronWalletPay invoice={invoice} onBroadcast={onBroadcast} />}

        {/* Reselect payment method */}
        {!hasPayment && onReset && (
          <Button variant="ghost" onClick={onReset} size="sm" className="w-full text-muted-foreground">
            <ArrowLeft className="size-3.5" />
            {t("payment.reselectMethod")}
          </Button>
        )}

        {/* Return to merchant */}
        {isCompleted && invoice.return_url && (
          <Button onClick={() => window.open(invoice.return_url, "_blank")} className="w-full">
            {t("payment.returnToMerchant")}
          </Button>
        )}
      </div>
    </div>
  )
}

export default PaymentAddress
