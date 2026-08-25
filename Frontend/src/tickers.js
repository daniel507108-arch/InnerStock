export const TICKERS = [
  { ticker: "AAPL", name: "Apple Inc." },
  { ticker: "MSFT", name: "Microsoft Corporation" },
  { ticker: "GOOGL", name: "Alphabet Inc." },
  { ticker: "AMZN", name: "Amazon.com Inc." },
  { ticker: "NVDA", name: "NVIDIA Corporation" },
  { ticker: "TSLA", name: "Tesla Inc." },
  { ticker: "META", name: "Meta Platforms Inc." },
  { ticker: "XEQT.TO", name: "iShares Core Equity ETF" },
  { ticker: "VFV.TO", name: "Vanguard S&P 500 Index ETF" },
  { ticker: "MRV.TO", name: "Ero Copper Corp." },
  { ticker: "MUU.TO", name: "Mainstreet Equity Corp." },
]

export function searchTickers(query) {
  const q = query.trim().toUpperCase()
  if (!q) return []
  return TICKERS.filter(
    (t) => t.ticker.startsWith(q) || t.name.toUpperCase().includes(q)
  ).slice(0, 8)
}