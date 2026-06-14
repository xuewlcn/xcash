// src/App.jsx
import { useEffect } from "react"
import { getUrlParam } from "@/lib/api"
import { useInvoice } from "@/hooks/useInvoice"
import { usePaymentMethod } from "@/hooks/usePaymentMethod"
import { useI18n } from "@/hooks/useI18n"
import useTheme from "@/hooks/useTheme"
import { getInvoiceDisplayStatus } from "@/lib/invoiceStatus"

import LoadingState from "@/components/LoadingState"
import ErrorState from "@/components/ErrorState"
import PaymentStepper from "@/components/PaymentStepper"

const BRAND_TITLE = "Xcash"

function buildDocumentTitle({ invoice, loading, error, t }) {
  if (loading) return `${BRAND_TITLE} · ${t("common.loading")}`
  if (error) return `${BRAND_TITLE} · ${t("common.error")}`
  if (!invoice) return BRAND_TITLE

  const displayStatus = getInvoiceDisplayStatus(invoice)
  const statusText = t(`invoice.status.${displayStatus}`) || displayStatus
  const amountText = [invoice.amount, invoice.currency].filter(Boolean).join(" ")
  return [BRAND_TITLE, statusText, amountText].filter(Boolean).join(" · ")
}

function App() {
  const { t } = useI18n()
  const { isDark, toggleTheme } = useTheme()
  const sysNo = getUrlParam("sys_no")
  const { invoice, loading, error, refetch } = useInvoice(sysNo)
  const {
    selectedCrypto,
    selectedChain,
    isSelecting,
    isEditing,
    error: paymentError,
    handleCryptoChange,
    handleChainChange,
    resetSelection,
    cancelEdit,
  } = usePaymentMethod(invoice, sysNo, refetch)

  useEffect(() => {
    document.title = buildDocumentTitle({ invoice, loading, error, t })
  }, [invoice, loading, error, t])

  if (loading) return <LoadingState />
  if (error) return <ErrorState error={error} onRetry={refetch} />
  if (!invoice) return <ErrorState error={t("error.invoiceNotFound")} onRetry={refetch} />

  return (
    <PaymentStepper
      invoice={invoice}
      selectedCrypto={selectedCrypto}
      selectedChain={selectedChain}
      isSelecting={isSelecting}
      isEditing={isEditing}
      paymentError={paymentError}
      handleCryptoChange={handleCryptoChange}
      handleChainChange={handleChainChange}
      resetSelection={resetSelection}
      cancelEdit={cancelEdit}
      isDark={isDark}
      toggleTheme={toggleTheme}
    />
  )
}

export default App
