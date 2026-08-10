import { Check } from "lucide-react"
import { useMetadataContext } from "@/context/MetadataContext"
import { sortChainOptions } from "@/lib/paymentMethodSort"
import { useI18n } from "@/hooks/useI18n"
import { cn } from "@/lib/utils"

function ChainSelector({ availableMethods, selectedCrypto, selectedChain, onChainChange, disabled = false }) {
  const { t } = useI18n()
  const { getChain } = useMetadataContext()

  if (!availableMethods || !selectedCrypto || !availableMethods[selectedCrypto]) {
    return (
      <div className="rounded-xl border border-dashed p-4 text-center">
        <p className="text-sm text-muted-foreground">
          {!selectedCrypto ? t("selector.selectTokenFirst") : t("selector.noNetworks")}
        </p>
      </div>
    )
  }

  const chainOptions = sortChainOptions(availableMethods[selectedCrypto])

  return (
    <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2" role="radiogroup" aria-label={t("selector.selectNetwork")}>
      {chainOptions.map((chain) => {
        const selected = chain === selectedChain
        const chainMeta = getChain(chain)

        return (
          <button
            key={chain}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChainChange(chain)}
            className={cn(
              "group flex min-h-16 items-center justify-between gap-3 rounded-xl border bg-card p-3.5 text-left shadow-xs transition-all duration-200",
              "hover:-translate-y-px hover:border-brand/50 hover:shadow-md focus-visible:border-ring focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-ring/40",
              selected && "border-brand bg-brand-soft/60 shadow-[0_0_18px_#72e8572e] ring-1 ring-brand/40 hover:shadow-[0_0_18px_#72e8572e]",
              disabled && "cursor-not-allowed opacity-60 hover:translate-y-0 hover:shadow-xs"
            )}
          >
            <span className="flex min-w-0 items-center gap-3">
              <span
                className={cn(
                  "flex size-10 shrink-0 items-center justify-center rounded-full bg-muted ring-1 ring-border transition-colors",
                  selected && "bg-card ring-brand/30"
                )}
              >
                <img
                  src={chainMeta.icon || undefined}
                  alt=""
                  className="size-7 rounded-full"
                  onError={(e) => { e.target.style.visibility = "hidden" }}
                />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold tracking-tight">{chainMeta.name}</span>
                <span
                  className={cn(
                    "mt-0.5 inline-flex items-center gap-1 rounded-full px-1.5 py-px text-[10px] font-medium",
                    chainMeta.isTestnet
                      ? "bg-warning-soft text-warning"
                      : "bg-success-soft text-success"
                  )}
                >
                  {chainMeta.isTestnet ? t("selector.testNetwork") : t("selector.mainNetwork")}
                </span>
              </span>
            </span>
            <span
              className={cn(
                "flex size-5 shrink-0 items-center justify-center rounded-full border transition-all",
                selected
                  ? "border-brand bg-brand text-brand-foreground"
                  : "border-border bg-transparent text-transparent group-hover:border-brand/40"
              )}
            >
              <Check className="size-3" />
            </span>
          </button>
        )
      })}
    </div>
  )
}

export default ChainSelector
