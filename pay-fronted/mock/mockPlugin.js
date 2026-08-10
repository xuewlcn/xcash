// Vite dev-server mock 中间件：为支付页提供 /v1 接口的本地演示实现。
// 仅在 `pnpm dev` 时生效；生产构建（vite build）完全不包含此逻辑。
//
// 用法：
//   http://localhost:5173/static/pay/?sys_no=DEMO&state=waiting
// state 可选：select(默认) | single | waiting | confirming | finalizing | completed | expired
import { metadata, buildInvoice, buildSelectedInvoice } from "./mockData.js"

function sendJson(res, status, payload) {
  res.statusCode = status
  res.setHeader("Content-Type", "application/json; charset=utf-8")
  res.end(JSON.stringify(payload))
}

function readBody(req) {
  return new Promise((resolve) => {
    let raw = ""
    req.on("data", (chunk) => (raw += chunk))
    req.on("end", () => {
      try {
        resolve(JSON.parse(raw || "{}"))
      } catch {
        resolve({})
      }
    })
  })
}

// state 参数可能打在页面 URL 上（?state=waiting），而前端拉账单时不会透传，
// 因此优先读请求自身的 query，其次读 Referer 页面 URL 的 query。
function resolveState(req, url) {
  const direct = url.searchParams.get("state")
  if (direct) return direct
  try {
    const referer = new URL(req.headers.referer || "")
    return referer.searchParams.get("state") || "select"
  } catch {
    return "select"
  }
}

export function payMockPlugin() {
  return {
    name: "xcash-pay-mock",
    configureServer(server) {
      server.middlewares.use(async (req, res, next) => {
        const url = new URL(req.url, "http://localhost")
        const path = url.pathname
        if (!path.startsWith("/v1/")) return next()

        if (path === "/v1/metadata" && req.method === "GET") {
          return sendJson(res, 200, metadata)
        }

        const selectMatch = path.match(/^\/v1\/invoice\/([^/]+)\/select-method$/)
        if (selectMatch && req.method === "POST") {
          const body = await readBody(req)
          const sysNo = decodeURIComponent(selectMatch[1])
          return sendJson(res, 200, buildSelectedInvoice(sysNo, body.crypto, body.chain))
        }

        const invoiceMatch = path.match(/^\/v1\/invoice\/([^/]+)$/)
        if (invoiceMatch && req.method === "GET") {
          const sysNo = decodeURIComponent(invoiceMatch[1])
          return sendJson(res, 200, buildInvoice(sysNo, resolveState(req, url)))
        }

        return sendJson(res, 404, { message: `mock: 未实现的接口 ${path}` })
      })
    },
  }
}
