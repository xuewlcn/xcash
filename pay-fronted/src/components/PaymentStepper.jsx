// src/components/PaymentStepper.jsx
import { useState, useEffect, useMemo, useRef, useCallback } from "react"
import { AlertCircle, Loader2, TimerOff } from "lucide-react"
import OrderSummaryPanel from "@/components/OrderSummaryPanel"
import StepIndicator from "@/components/StepIndicator"
import StepCompleted from "@/components/StepCompleted"
import PaymentMethodSelector from "@/components/PaymentMethodSelector"
import PaymentAddress from "@/components/PaymentAddress"
import WaitingPayment from "@/components/WaitingPayment"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { useI18n } from "@/hooks/useI18n"
import { isPaymentConfirming } from "@/lib/invoiceStatus"

function ExpiredOrderCard() {
  const { t } = useI18n()

  return (
    <div className="animate-in fade-in-0 slide-in-from-bottom-2 duration-300">
      <div className="glow-card overflow-hidden rounded-2xl border bg-card shadow-md">
        {/* 头部：与收款卡同语言 —— 红色着色横幅 + 图标方块 + 状态胶囊 */}
        <div className="flex items-center gap-3.5 border-b bg-gradient-to-br from-[#e5484d17] via-transparent to-transparent px-6 py-5 dark:from-[#ff5f5712]">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl bg-destructive/10 ring-1 ring-destructive/30">
            <TimerOff className="size-5 text-destructive" />
          </span>
          <div className="min-w-0 flex-1">
            <h2 className="text-base font-semibold tracking-tight">{t("expired.orderExpired")}</h2>
            <p className="mt-0.5 text-sm text-muted-foreground">{t("expired.contactMerchant")}</p>
          </div>
          <span className="inline-flex shrink-0 items-center gap-1.5 rounded-full border border-destructive/30 bg-destructive/10 px-2.5 py-1 text-xs font-medium text-destructive">
            <span className="size-1.5 rounded-full bg-current" />
            {t("invoice.status.expired")}
          </span>
        </div>

        <div className="px-6 py-6">
          <Button
            variant="outline"
            className="w-full"
            onClick={() => window.location.reload()}
          >
            {t("expired.refreshPage")}
          </Button>
        </div>
      </div>
    </div>
  )
}

function PaymentStepper({
  invoice,
  selectedCrypto,
  selectedChain,
  isSelecting,
  isEditing,
  paymentError,
  handleCryptoChange,
  handleChainChange,
  resetSelection,
  cancelEdit,
  isDark,
  toggleTheme,
}) {
  const { t } = useI18n()
  const hasPaymentMethod = Boolean(
    invoice.crypto && invoice.chain && invoice.pay_address && invoice.pay_amount
  )
  const hasPayment = Boolean(invoice.payment)
  const isCompleted = invoice.status === "completed"
  const isConfirming = isPaymentConfirming(invoice)
  const isWaiting = invoice.status === "waiting"
  const isExpired = invoice.status === "expired"
  const availableMethods = invoice.methods ?? {}

  // Detect single-method: 1 token with 1 chain → skip selection step, show 3-step flow
  const methodTokens = Object.keys(availableMethods)
  const isSingleMethod = methodTokens.length === 1 && availableMethods[methodTokens[0]]?.length === 1
  const singleToken = isSingleMethod ? methodTokens[0] : null
  const singleChain = isSingleMethod ? availableMethods[methodTokens[0]][0] : null
  const stepCount = isSingleMethod ? 2 : 3

  // Auto-select token when only one payable method exists.
  useEffect(() => {
    if (isSingleMethod && isWaiting && !hasPaymentMethod && !selectedCrypto && !isSelecting) {
      handleCryptoChange(singleToken)
    }
  }, [isSingleMethod, isWaiting, hasPaymentMethod, selectedCrypto, isSelecting, singleToken, handleCryptoChange])

  // Auto-select chain once token is set; usePaymentMethod then submits select-method.
  useEffect(() => {
    if (isSingleMethod && isWaiting && !hasPaymentMethod && selectedCrypto && !selectedChain && !isSelecting) {
      handleChainChange(singleChain)
    }
  }, [isSingleMethod, isWaiting, hasPaymentMethod, selectedCrypto, selectedChain, isSelecting, singleChain, handleChainChange])

  const naturalStep = useMemo(() => {
    if (isExpired) return 1
    if (isSingleMethod) {
      if (isCompleted) return 2
      return 1
    }
    if (isCompleted) return 3
    if (isConfirming || (hasPaymentMethod && !isEditing)) return 2
    return 1
  }, [isCompleted, isConfirming, hasPaymentMethod, isEditing, isExpired, isSingleMethod])

  // 有链上 payment 或已分配当前支付指引时直接跳到当前 naturalStep。
  const initialStep = hasPayment || hasPaymentMethod ? naturalStep : 1
  const [activeStep, setActiveStep] = useState(initialStep)
  const maxNaturalStepRef = useRef(initialStep)

  // 钱包一键支付广播成功后置位：让下方总状态卡从「请尽快完成支付」切到「等待区块确认」，
  // 与支付卡片内「交易已提交」一致。支付目标(pay_address)变化时复位，避免重选后残留。
  const [broadcasted, setBroadcasted] = useState(false)
  const handleWalletBroadcast = useCallback(() => setBroadcasted(true), [])
  useEffect(() => {
    setBroadcasted(false)
  }, [invoice.pay_address])

  // Auto-advance only when server state moves forward.
  useEffect(() => {
    if (naturalStep > maxNaturalStepRef.current) {
      maxNaturalStepRef.current = naturalStep
      setActiveStep(naturalStep)
    } else {
      maxNaturalStepRef.current = Math.max(maxNaturalStepRef.current, naturalStep)
    }
  }, [naturalStep])

  const handleStepClick = (step) => {
    if (isCompleted) return
    if (step >= naturalStep) return
    if (!isSingleMethod && step === 1 && naturalStep >= 2) {
      resetSelection()
    }
    // 用户主动回退时重置历史最大步数，否则重选相同支付方式后
    // naturalStep 恢复到原值时不会触发自动前进（因为不大于历史最大值）。
    maxNaturalStepRef.current = step
    setActiveStep(step)
  }

  // Step index aliases
  const methodStep = 1
  const sendStep = isSingleMethod ? 1 : 2
  const completedStep = isSingleMethod ? 2 : 3

  return (
    <div className="checkout-backdrop min-h-svh bg-background">
      <div className="mx-auto flex min-h-svh max-w-6xl flex-col lg:flex-row">
        <OrderSummaryPanel invoice={invoice} isDark={isDark} toggleTheme={toggleTheme} />

        {/* 右侧：步骤 + 内容 + 页脚 */}
        <div className="flex min-w-0 flex-1 flex-col">
          {!isExpired && (
            <StepIndicator
              activeStep={activeStep}
              naturalStep={naturalStep}
              onStepClick={handleStepClick}
              stepCount={stepCount}
              lockBack={isCompleted}
            />
          )}

          <main className="flex-1 px-4 pb-16 pt-6 sm:px-8 lg:pt-10">
            <div className="mx-auto w-full max-w-xl">

              {isExpired && (
                <ExpiredOrderCard />
              )}

              {!isExpired && !isSingleMethod && activeStep === methodStep && (
                <div className="animate-in fade-in-0 slide-in-from-bottom-2 duration-300">
                  <PaymentMethodSelector
                    invoice={invoice}
                    availableMethods={availableMethods}
                    selectedCrypto={selectedCrypto}
                    selectedChain={selectedChain}
                    onCryptoChange={handleCryptoChange}
                    onChainChange={handleChainChange}
                    isSelecting={isSelecting}
                    isEditing={isEditing}
                    error={paymentError}
                    onCancelEdit={cancelEdit}
                  />
                </div>
              )}

              {!isExpired && activeStep === sendStep && (
                <div className="space-y-4 animate-in fade-in-0 slide-in-from-bottom-2 duration-300">
                  {paymentError && !hasPaymentMethod ? (
                    <Alert variant="destructive">
                      <AlertCircle />
                      <AlertTitle>{t("common.error")}</AlertTitle>
                      <AlertDescription>{paymentError}</AlertDescription>
                    </Alert>
                  ) : isSelecting || (isSingleMethod && isWaiting && !hasPaymentMethod) ? (
                    <div className="flex flex-col items-center gap-4 py-16">
                      <Loader2 className="size-8 animate-spin text-primary" />
                      <p className="text-sm text-muted-foreground">{t("payment.gettingPaymentInfo")}</p>
                    </div>
                  ) : (
                    <>
                      <PaymentAddress
                        invoice={invoice}
                        onBroadcast={handleWalletBroadcast}
                        onReset={isWaiting && !hasPayment && !isSingleMethod ? () => {
                          resetSelection()
                          maxNaturalStepRef.current = methodStep
                          setActiveStep(methodStep)
                        } : null}
                      />
                      {isWaiting && hasPaymentMethod && !hasPayment && !isEditing && !isExpired && (
                        <WaitingPayment broadcasted={broadcasted} />
                      )}
                    </>
                  )}
                </div>
              )}

              {!isExpired && activeStep === completedStep && (
                <StepCompleted invoice={invoice} />
              )}

            </div>
          </main>

          {/* Footer */}
          <footer className="px-4 pb-6 pt-2">
            <div className="mx-auto flex max-w-xl items-center justify-center gap-2 text-xs text-muted-foreground">
              <span>Powered by</span>
              <a href="https://xca.sh" className="font-semibold text-brand-gradient hover:opacity-80">
                Xcash
              </a>
              <span className="text-border">|</span>
              <span>Secure Crypto Payments</span>
            </div>
          </footer>
        </div>
      </div>
    </div>
  )
}

export default PaymentStepper
