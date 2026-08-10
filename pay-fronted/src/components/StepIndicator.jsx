// src/components/StepIndicator.jsx
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"
import { useI18n } from "@/hooks/useI18n"

const STEP_KEYS = {
  3: ["invoice.stepLabel", "payment.sendLabel", "invoice.completedLabel"],
  2: ["payment.sendLabel", "invoice.completedLabel"],
}

function StepIndicator({ activeStep, naturalStep, onStepClick, stepCount = 3, lockBack = false }) {
  const { t } = useI18n()
  const keys = STEP_KEYS[stepCount] ?? STEP_KEYS[3]
  const nodes = Array.from({ length: stepCount }, (_, i) => i + 1)
  const gridStyle = { gridTemplateColumns: `repeat(${stepCount}, minmax(0, 1fr))` }

  const isFlowComplete = lockBack && naturalStep >= stepCount
  const isDone = (n) => n < naturalStep && n !== activeStep
  const isSuccess = (n) => isDone(n) || (isFlowComplete && n <= naturalStep)
  const isClickable = (n) => !lockBack && n < naturalStep && n !== activeStep

  return (
    <div className="px-6 pt-6 sm:px-8 lg:pt-10">
      <div className="mx-auto max-w-xl">
        {/* Nodes + lines */}
        <div className="grid items-center" style={gridStyle}>
          {nodes.map((n, i) => (
            <div key={n} className="relative flex justify-center">
              <button
                onClick={() => isClickable(n) && onStepClick?.(n)}
                disabled={!isClickable(n)}
                className={cn(
                  "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold transition-all outline-none",
                  isSuccess(n)
                    ? "bg-success text-success-foreground shadow-[0_0_10px_#72e85759]"
                    : n <= activeStep
                      ? "bg-primary text-primary-foreground shadow-[0_0_0_4px_var(--brand-soft),0_0_16px_#72e85780]"
                      : "border bg-card text-muted-foreground",
                  isClickable(n) && "cursor-pointer hover:scale-105"
                )}
                aria-label={`${t("payment.step")} ${n}: ${t(keys[i])}`}
              >
                {isSuccess(n) ? <Check className="size-3.5" /> : n}
              </button>
              {n < stepCount && (
                <div className="absolute left-[calc(50%+1.125rem)] right-[calc(-50%+1.125rem)] top-1/2 h-0.5 -translate-y-1/2 overflow-hidden rounded-full bg-border">
                  <div
                    className={cn(
                      "h-full rounded-full bg-gradient-to-r from-[#3dcf40] to-[#72e857] shadow-[0_0_8px_#72e85773] transition-all duration-500",
                      n < naturalStep ? "w-full" : "w-0"
                    )}
                  />
                </div>
              )}
            </div>
          ))}
        </div>

        {/* Labels */}
        <div className="mt-2.5 grid" style={gridStyle}>
          {nodes.map((n, i) => (
            <div
              key={n}
              className={cn(
                "min-w-0 whitespace-nowrap px-1 text-center text-[11px] font-medium leading-tight tracking-wide",
                isSuccess(n)
                  ? "text-success"
                  : n === activeStep
                    ? "text-brand font-semibold"
                    : "text-muted-foreground"
              )}
            >
              {t(keys[i])}
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default StepIndicator
