const CRYPTO_PRIORITY = ["USDT", "USDC", "DAI"]
const CHAIN_PRIORITY = ["ethereum", "tron", "bsc"]

function sortByPriority(values, getPriorityKey) {
  return values
    .map((value, index) => {
      const priority = getPriorityKey(value)
      return {
        value,
        index,
        priority: priority === -1 ? Number.MAX_SAFE_INTEGER : priority,
      }
    })
    .sort((left, right) => left.priority - right.priority || left.index - right.index)
    .map(({ value }) => value)
}

export function sortCryptoOptions(cryptos) {
  return sortByPriority(cryptos, (crypto) => CRYPTO_PRIORITY.indexOf(crypto.toUpperCase()))
}

export function sortChainOptions(chains) {
  return sortByPriority(chains, (chain) => {
    const chainFamily = chain.toLowerCase().split("-")[0]
    return CHAIN_PRIORITY.indexOf(chainFamily)
  })
}
