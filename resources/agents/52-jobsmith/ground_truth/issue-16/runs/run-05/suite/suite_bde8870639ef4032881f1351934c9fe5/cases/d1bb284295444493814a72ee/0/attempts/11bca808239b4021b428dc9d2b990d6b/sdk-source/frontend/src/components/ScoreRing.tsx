import { useEffect, useId, useState } from "react"

const TIERS = {
  emerald: ["#34d399", "#059669"],
  amber: ["#fbbf24", "#d97706"],
  rose: ["#fb7185", "#e11d48"],
} as const

// 分數環：漸層描邊、依分數變色、掛載時動畫掃出。
export function ScoreRing({ score, size = 120 }: { score: number; size?: number }) {
  const gid = "ring-" + useId().replace(/:/g, "")
  const stroke = Math.max(8, Math.round(size * 0.1))
  const cx = size / 2
  const r = (size - stroke) / 2
  const c = 2 * Math.PI * r
  const [shown, setShown] = useState(0)
  useEffect(() => {
    const t = requestAnimationFrame(() => setShown(score))
    return () => cancelAnimationFrame(t)
  }, [score])
  const clamped = Math.max(0, Math.min(100, shown))
  const offset = c * (1 - clamped / 100)
  const tier = score >= 80 ? "emerald" : score >= 60 ? "amber" : "rose"
  const [from, to] = TIERS[tier]
  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor={from} />
          <stop offset="1" stopColor={to} />
        </linearGradient>
      </defs>
      <circle cx={cx} cy={cx} r={r} fill="none" stroke="#e2e8f0" strokeWidth={stroke} />
      <circle
        cx={cx} cy={cx} r={r} fill="none" stroke={`url(#${gid})`} strokeWidth={stroke}
        strokeDasharray={c} strokeDashoffset={offset} strokeLinecap="round"
        transform={`rotate(-90 ${cx} ${cx})`}
        style={{ transition: "stroke-dashoffset 0.9s ease-out" }}
      />
      <text x={cx} y={cx} dy={size * 0.02} textAnchor="middle" dominantBaseline="middle"
        fontSize={size * 0.28} fontWeight="700" fill="#0f172a">{score}</text>
      <text x={cx} y={cx + size * 0.2} textAnchor="middle" fontSize={size * 0.1} fill="#64748b">/ 100</text>
    </svg>
  )
}
