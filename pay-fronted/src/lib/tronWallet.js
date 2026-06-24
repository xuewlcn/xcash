// TronLink 钱包工具：纯浏览器原生能力，零额外依赖。
// 所有 Tron 交互直接走 TronLink 注入的 window.tronLink（请求授权）与
// window.tronWeb（TronWeb 实例，构造/广播交易）。
// 绝不引入 tronweb 等库，能力全部来自钱包注入对象。

/**
 * 读取 TronLink 注入对象。
 * 必须同时存在 tronLink（授权入口）与 tronWeb（交易能力）才算可用。
 */
export function getTron() {
  if (typeof window === "undefined") {
    return null
  }
  return window.tronLink && window.tronWeb
    ? { tronLink: window.tronLink, tronWeb: window.tronWeb }
    : null
}

/**
 * 订阅 TronLink 可用性变化。
 *
 * TronLink 是异步注入的：页面加载完才挂上 window.tronWeb，故不能只在挂载时检测一次。
 * 这里三管齐下保证稳健：
 *   1) 挂载即用当前状态回调一次；
 *   2) 监听 window 的 `tronLink#initialized` 事件，注入完成后再回调 true；
 *   3) 设一个 ~800ms 兜底定时器再检测一次，覆盖事件错过的情况。
 * 返回清理函数：移除监听 + 清除定时器，避免对已卸载组件回调。
 */
export function subscribeTron(cb) {
  if (typeof window === "undefined") {
    cb(false)
    return () => {}
  }

  // 1) 立即用当前状态回调一次。
  cb(Boolean(getTron()))

  // 2) TronLink 注入完成事件：注入完成意味着对象就绪，回调 true。
  const onInitialized = () => cb(true)
  window.addEventListener("tronLink#initialized", onInitialized)

  // 3) 兜底再检测：覆盖事件已在挂载前触发、被错过的情况。
  const timer = window.setTimeout(() => {
    cb(Boolean(getTron()))
  }, 800)

  return () => {
    window.removeEventListener("tronLink#initialized", onInitialized)
    window.clearTimeout(timer)
  }
}

/**
 * 请求 TronLink 授权并返回当前 base58 地址。
 *
 * TronLink 约定：tron_requestAccounts 返回对象的 code === 200 为通过、4001 为用户拒绝。
 * 通过后还需等 tronWeb.ready 与 defaultAddress.base58 就绪才拿得到地址。
 * 用户拒绝时抛带 code:4001 的错误，供 normalizeTronError 区分；拿不到地址则抛通用错误。
 */
export async function connectTron() {
  const res = await window.tronLink.request({
    method: "tron_requestAccounts",
  })
  // 用户在 TronLink 弹窗中拒绝授权。
  if (res?.code === 4001) {
    throw Object.assign(new Error("rejected"), { code: 4001 })
  }
  // 非 200 视为授权未通过（含未解锁等情况）。
  if (res?.code !== 200) {
    throw new Error("tron_requestAccounts failed")
  }

  // 授权通过后，tronWeb 可能还没把账户写入，取地址前确认 ready 与地址都就绪。
  const address = window.tronWeb?.ready
    ? window.tronWeb?.defaultAddress?.base58
    : null
  if (!address) {
    throw new Error("tron address unavailable")
  }
  return address
}

/**
 * 校验 TronLink 当前网络与账单期望（主网/测试网）是否一致。
 *
 * 通过 tronWeb.fullNode.host 判定：host 含 "nile" / "shasta" 视为测试网，否则视为主网。
 * 仅当能明确判定且与 isTestnet 冲突时才抛 NETWORK_MISMATCH 阻断；
 * 自定义节点等无已知标记的 host 一律放行，不误伤。
 */
export function checkTronNetwork(isTestnet) {
  const host = window.tronWeb?.fullNode?.host
  if (typeof host !== "string") {
    // 拿不到 host，无法判定，放行。
    return
  }
  const lower = host.toLowerCase()
  // 已知测试网标记；命中则判为测试网。
  const hostIsTestnet = lower.includes("nile") || lower.includes("shasta")
  // 仅当能明确判出网络类型且与期望冲突时阻断。
  const known = hostIsTestnet || isKnownMainnetHost(lower)
  if (known && hostIsTestnet !== Boolean(isTestnet)) {
    throw Object.assign(new Error("network mismatch"), {
      code: "NETWORK_MISMATCH",
    })
  }
}

/**
 * 判定 host 是否为已知 Tron 主网节点。
 * 仅识别官方主网域名，自定义节点返回 false（交由上层放行，不阻断）。
 */
function isKnownMainnetHost(lowerHost) {
  return (
    lowerHost.includes("trongrid.io") || lowerHost.includes("tronstack.io")
  )
}

/**
 * 通过 TronLink 发起一笔付款，返回交易哈希（txid）。
 *
 * 金额一律取后端给的最小单位整数字符串（TRX=sun，TRC20=代币精度），前端不重算。
 *   - 原生 TRX：tronWeb.trx.sendTransaction 直接转账；
 *   - TRC20：取合约实例后调 transfer(to, amount).send({ feeLimit })。
 * 不触碰账单状态：拿到 txid 仅代表已广播，确认由账单轮询裁定。
 */
export async function sendTronPayment({
  is_native,
  to,
  contract,
  amount,
  fee_limit,
}) {
  if (is_native) {
    // 原生 TRX 转账：amount 为 sun，需转成 Number。
    const res = await window.tronWeb.trx.sendTransaction(to, Number(amount))
    return res?.txid || res?.transaction?.txID
  }
  // TRC20 转账：amount 原样传字符串（代币精度的最小单位）。
  const c = await window.tronWeb.contract().at(contract)
  const txid = await c.transfer(to, amount).send({ feeLimit: fee_limit })
  return txid
}

/**
 * 归一化 Tron 交互错误为上层可据此选 i18n 文案的标记。
 * 4001：用户拒绝；NETWORK_MISMATCH：网络不匹配；其余为通用失败。
 */
export function normalizeTronError(e) {
  if (e?.code === 4001) {
    return { kind: "rejected" }
  }
  if (e?.code === "NETWORK_MISMATCH") {
    return { kind: "networkMismatch" }
  }
  return { kind: "failed", message: e?.message }
}
