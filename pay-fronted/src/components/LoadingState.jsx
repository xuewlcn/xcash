import { Loader2 } from "lucide-react"
import BrandHeading from "@/components/BrandHeading"
import { useI18n } from "@/hooks/useI18n"

function LoadingState() {
  const { t } = useI18n()

  return (
    <div className="checkout-backdrop flex min-h-svh flex-col items-center justify-center bg-background">
      <div className="flex flex-col items-center gap-10 text-center">
        <BrandHeading size={44} />
        <div className="flex flex-col items-center gap-4">
          <span className="relative flex size-10 items-center justify-center">
            <span className="absolute inset-0 rounded-full bg-brand/15" />
            <Loader2 className="size-6 animate-spin text-brand" />
          </span>
          <p className="text-sm text-muted-foreground">{t("common.loading")}</p>
        </div>
      </div>
    </div>
  )
}

export default LoadingState
