import { Check } from "lucide-react"
import { getChainIconUrl, getChainDisplayName, isTestnet } from "@/lib/cryptoIcons"
import { sortChainOptions } from "@/lib/paymentMethodSort"
import { useI18n } from "@/hooks/useI18n"
import { cn } from "@/lib/utils"

function ChainSelector({ availableMethods, selectedCrypto, selectedChain, onChainChange, disabled = false }) {
  const { t } = useI18n()

  if (!availableMethods || !selectedCrypto || !availableMethods[selectedCrypto]) {
    return (
      <div className="p-4 border border-dashed rounded-md text-center">
        <p className="text-sm text-muted-foreground">
          {!selectedCrypto ? t("selector.selectTokenFirst") : t("selector.noNetworks")}
        </p>
      </div>
    )
  }

  const chainOptions = sortChainOptions(availableMethods[selectedCrypto])

  return (
    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2" role="radiogroup" aria-label={t("selector.selectNetwork")}>
      {chainOptions.map((chain) => {
        const selected = chain === selectedChain

        return (
          <button
            key={chain}
            type="button"
            role="radio"
            aria-checked={selected}
            disabled={disabled}
            onClick={() => onChainChange(chain)}
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
                  src={getChainIconUrl(chain)}
                  alt=""
                  className="size-6 rounded-full"
                  onError={(e) => { e.target.style.visibility = "hidden" }}
                />
              </span>
              <span className="min-w-0">
                <span className="block truncate text-sm font-semibold">{getChainDisplayName(chain)}</span>
                <span className="block truncate text-xs text-muted-foreground">
                  {isTestnet(chain) ? t("selector.testNetwork") : t("selector.mainNetwork")}
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

export default ChainSelector
