import { Check } from "lucide-react"
import { getCryptoIconUrl, getCryptoDisplayName } from "@/lib/cryptoIcons"
import { sortCryptoOptions } from "@/lib/paymentMethodSort"
import { useI18n } from "@/hooks/useI18n"
import { cn } from "@/lib/utils"

function TokenSelector({ availableMethods, selectedCrypto, onCryptoChange, disabled = false }) {
  const { t } = useI18n()

  if (!availableMethods || Object.keys(availableMethods).length === 0) {
    return (
      <div className="p-4 border border-dashed rounded-md text-center">
        <p className="text-sm text-muted-foreground">{t("selector.noTokens")}</p>
      </div>
    )
  }

  const tokenOptions = sortCryptoOptions(Object.keys(availableMethods))

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t("selector.selectToken")}>
      {tokenOptions.map((token) => {
        const selected = token === selectedCrypto

        return (
          <button
            key={token}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onCryptoChange(token)}
            className={cn(
              "flex min-h-14 items-center justify-between gap-3 rounded-md border bg-background p-3 text-left shadow-xs transition-all",
              "hover:border-primary/50 hover:bg-accent focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
              selected && "border-primary bg-accent text-accent-foreground ring-1 ring-primary/20",
              disabled && "cursor-not-allowed opacity-60"
            )}
          >
            <span className="flex min-w-0 items-center gap-2.5">
              <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-muted">
                <img
                  src={getCryptoIconUrl(token)}
                  alt=""
                  className="size-6 rounded-full"
                  onError={(e) => { e.target.style.visibility = "hidden" }}
                />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{getCryptoDisplayName(token)}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {availableMethods[token].length} {t("selector.networks")}
                </span>
              </span>
            </span>
            {selected && (
              <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-primary text-primary-foreground">
                <Check className="size-3" />
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}

export default TokenSelector
