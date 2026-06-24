import { useCallback, useEffect, useState } from "react"
import {
  connect,
  ensureChain,
  normalizeError,
  sendPayment,
  subscribeProviders,
} from "@/lib/wallet"

/**
 * 注入式 EVM 钱包支付 Hook。
 *
 * 维护已发现的钱包列表，并暴露 pay 方法走「连接 → 切链 → 发送」三段流程。
 * 仅负责广播交易拿到 txhash，绝不触碰账单状态——账单确认仍由 useInvoice 轮询驱动。
 *
 * 返回：
 * - available：账单是否支持钱包支付（由后端 evm_payment 决定，与是否装钱包无关）
 * - wallets：已发现的钱包数组（含兜底项）
 * - status：idle | connecting | switching | sending | submitted | error
 * - error：normalizeError 结果，仅在 status === 'error' 时有意义
 * - txHash：广播成功后的交易哈希
 * - pay(provider)：对指定钱包发起支付
 */
export function useWalletPayment(invoice) {
  const [wallets, setWallets] = useState([])
  const [status, setStatus] = useState("idle")
  const [error, setError] = useState(null)
  const [txHash, setTxHash] = useState(null)

  const evmPayment = invoice?.evm_payment
  const available = Boolean(evmPayment)

  // 订阅钱包发现：组件挂载时拿一次当前列表，后续每有新钱包 announce 都更新；
  // 卸载时取消订阅，避免对已卸载组件 setState。
  useEffect(() => {
    const unsubscribe = subscribeProviders((list) => {
      setWallets(list)
    })
    return unsubscribe
  }, [])

  const pay = useCallback(
    async (provider) => {
      if (!evmPayment || !provider) {
        return
      }
      // 每次发起支付前清空上一轮的错误/哈希，状态机从头走起。
      setError(null)
      setTxHash(null)
      try {
        setStatus("connecting")
        const from = await connect(provider)

        setStatus("switching")
        await ensureChain(provider, evmPayment.chain_id)

        setStatus("sending")
        const hash = await sendPayment(provider, {
          from,
          to: evmPayment.to,
          value: evmPayment.value,
          data: evmPayment.data,
        })

        // 仅标记「已提交」，真正的确认交给账单轮询，前端不擅自标记已支付。
        setTxHash(hash)
        setStatus("submitted")
      } catch (e) {
        setError(normalizeError(e))
        setStatus("error")
      }
    },
    [evmPayment]
  )

  return { available, wallets, status, error, txHash, pay }
}
