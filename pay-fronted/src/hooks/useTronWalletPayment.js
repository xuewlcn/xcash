import { useCallback, useEffect, useState } from "react"
import {
  checkTronNetwork,
  connectTron,
  getTron,
  normalizeTronError,
  sendTronPayment,
  subscribeTron,
} from "@/lib/tronWallet"

/**
 * TronLink 钱包支付 Hook。
 *
 * 走「连接（含网络校验）→ 发送」两段流程，仅广播交易拿到 txid，绝不触碰账单状态——
 * 账单确认仍由 useInvoice 轮询驱动。Tron 没有「自动切链」能力，故网络校验并入连接阶段。
 *
 * 返回：
 * - available：账单是否支持 Tron 钱包支付（由后端 tron_payment 决定，与是否装钱包无关）
 * - hasWallet：是否检测到 TronLink（异步注入，订阅维护）
 * - status：idle | connecting | sending | submitted | error
 * - error：normalizeTronError 结果，仅在 status === 'error' 时有意义
 * - txHash：广播成功后的交易哈希
 * - pay()：发起支付（Tron 为单钱包，无需传 provider）
 */
export function useTronWalletPayment(invoice) {
  const [hasWallet, setHasWallet] = useState(() => Boolean(getTron()))
  const [status, setStatus] = useState("idle")
  const [error, setError] = useState(null)
  const [txHash, setTxHash] = useState(null)

  const tronPayment = invoice?.tron_payment
  const available = Boolean(tronPayment)

  // 订阅 TronLink 可用性：异步注入，挂载即检测、注入完成后再更新；
  // 卸载时清理（移除监听 + 清定时器），避免对已卸载组件 setState。
  useEffect(() => {
    const unsubscribe = subscribeTron((ok) => {
      setHasWallet(ok)
    })
    return unsubscribe
  }, [])

  const pay = useCallback(async () => {
    if (!tronPayment) {
      return
    }
    // 每次发起前清空上一轮的错误/哈希，状态机从头走起。
    setError(null)
    setTxHash(null)
    try {
      // 连接 + 网络校验合并为 connecting 阶段（Tron 无切链步骤）。
      setStatus("connecting")
      await connectTron()
      checkTronNetwork(tronPayment.is_testnet)

      setStatus("sending")
      const hash = await sendTronPayment(tronPayment)

      // 仅标记「已提交」，真正的确认交给账单轮询，前端不擅自标记已支付。
      setTxHash(hash)
      setStatus("submitted")
    } catch (e) {
      setError(normalizeTronError(e))
      setStatus("error")
    }
  }, [tronPayment])

  return { available, hasWallet, status, error, txHash, pay }
}
