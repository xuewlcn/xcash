// 本地开发演示数据：仅供 vite dev server 的 mock 中间件使用，不参与生产构建。

function tokenIcon(color, letter) {
  const svg =
    `<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'>` +
    `<circle cx='16' cy='16' r='16' fill='${color}'/>` +
    `<text x='16' y='21.5' font-size='14' font-family='Arial,sans-serif' font-weight='700' fill='#ffffff' text-anchor='middle'>${letter}</text>` +
    `</svg>`
  return `data:image/svg+xml,${encodeURIComponent(svg)}`
}

export const metadata = {
  chains: [
    { code: "ethereum", name: "Ethereum", icon: tokenIcon("#627eea", "E"), is_testnet: false },
    { code: "tron", name: "TRON", icon: tokenIcon("#eb0029", "T"), is_testnet: false },
    { code: "bsc", name: "BNB Chain", icon: tokenIcon("#f0b90b", "B"), is_testnet: false },
    { code: "polygon", name: "Polygon", icon: tokenIcon("#8247e5", "P"), is_testnet: false },
    { code: "arbitrum-one", name: "Arbitrum One", icon: tokenIcon("#28a0f0", "A"), is_testnet: false },
    { code: "bitcoin", name: "Bitcoin", icon: tokenIcon("#f7931a", "B"), is_testnet: false },
  ],
  cryptos: [
    { symbol: "USDT", name: "Tether USD", icon: tokenIcon("#26a17b", "₮") },
    { symbol: "USDC", name: "USD Coin", icon: tokenIcon("#2775ca", "$") },
    { symbol: "ETH", name: "Ethereum", icon: tokenIcon("#627eea", "Ξ") },
    { symbol: "BTC", name: "Bitcoin", icon: tokenIcon("#f7931a", "₿") },
  ],
}

const METHODS = {
  USDT: ["tron", "ethereum", "bsc", "polygon"],
  USDC: ["ethereum", "polygon", "arbitrum-one"],
  ETH: ["ethereum", "arbitrum-one"],
  BTC: ["bitcoin"],
}

const SINGLE_METHODS = { USDT: ["tron"] }

const PAY_DETAILS = {
  crypto: "USDT",
  chain: "tron",
  pay_address: "TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE",
  pay_amount: "128.560000",
  crypto_address: "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",
  payment_uri: "tron:TQn9Y2khEsLJW1ChVWFMSMeRDow5KcbLSE?amount=128.56&token=USDT",
}

const TX_HASH = "0x8f3cf7ad23cd3cadbd9735aff958023eff958023c96a8c94a5d8b0e2f3a1b2c3"

function baseInvoice(sysNo) {
  return {
    sys_no: sysNo,
    out_no: "M202407308821",
    title: "Xcash Pro 年度订阅",
    amount: "128.56",
    currency: "USD",
    return_url: "https://example.com/orders/M202407308821",
  }
}

// 确认进度随轮询缓慢推进，让确认中状态在本地也能看到动态效果。
const confirmingStartedAt = Date.now()

export function buildInvoice(sysNo, state) {
  const invoice = baseInvoice(sysNo)

  switch (state) {
    case "single":
      return { ...invoice, status: "waiting", methods: SINGLE_METHODS }
    case "select":
      return { ...invoice, status: "waiting", methods: METHODS }
    case "waiting":
      return {
        ...invoice,
        status: "waiting",
        methods: METHODS,
        ...PAY_DETAILS,
        expires_at: new Date(Date.now() + 25 * 60 * 1000).toISOString(),
      }
    case "confirming": {
      const progress = Math.min(95, 20 + Math.floor((Date.now() - confirmingStartedAt) / 1000) * 3)
      return {
        ...invoice,
        status: "waiting",
        methods: METHODS,
        ...PAY_DETAILS,
        expires_at: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
        payment: {
          status: "confirming",
          hash: TX_HASH,
          confirm_progress: {
            progress,
            has_confirmed_count: Math.floor((progress / 100) * 12),
            need_confirmed_count: 12,
          },
        },
      }
    }
    case "finalizing":
      return {
        ...invoice,
        status: "waiting",
        methods: METHODS,
        ...PAY_DETAILS,
        expires_at: new Date(Date.now() + 20 * 60 * 1000).toISOString(),
        payment: {
          status: "confirming",
          hash: TX_HASH,
          confirm_progress: { progress: 100, has_confirmed_count: 12, need_confirmed_count: 12 },
        },
      }
    case "completed":
      return {
        ...invoice,
        status: "completed",
        methods: METHODS,
        ...PAY_DETAILS,
        payment: {
          status: "completed",
          hash: TX_HASH,
          confirm_progress: { progress: 100, has_confirmed_count: 12, need_confirmed_count: 12 },
        },
      }
    case "expired":
      return {
        ...invoice,
        status: "expired",
        methods: METHODS,
        expires_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
      }
    default:
      return { ...invoice, status: "waiting", methods: METHODS }
  }
}

// 模拟 select-method：按用户选择回填支付指引，返回完整账单。
export function buildSelectedInvoice(sysNo, crypto, chain) {
  return {
    ...baseInvoice(sysNo),
    status: "waiting",
    methods: METHODS,
    crypto,
    chain,
    pay_address: chain === "tron" ? PAY_DETAILS.pay_address : "0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE",
    pay_amount: crypto === "BTC" ? "0.00126000" : crypto === "ETH" ? "0.03600000" : "128.560000",
    crypto_address: crypto === "USDT" || crypto === "USDC" ? PAY_DETAILS.crypto_address : null,
    payment_uri: `ethereum:0x3f5CE5FBFe3E9af3971dD833D26bA9b5C936f0bE?value=128.56`,
    expires_at: new Date(Date.now() + 30 * 60 * 1000).toISOString(),
  }
}
