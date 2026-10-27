// 品牌：紙飛機圖記（投遞 + co-pilot；origami 兩面摺痕）+ wordmark。
export function Logomark({ size = 40 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <defs>
        <linearGradient id="brandLogo" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#4f46e5" />
          <stop offset="1" stopColor="#9333ea" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="url(#brandLogo)" />
      <g transform="translate(4 4)">
        <path d="M22 2 2 9 11 13Z" fill="#fff" />
        <path d="M22 2 11 13 15 22Z" fill="#fff" fillOpacity="0.72" />
      </g>
    </svg>
  )
}

export function Brand({ size = "md" }: { size?: "sm" | "md" }) {
  return (
    <div className="flex items-center gap-2.5">
      <Logomark size={size === "sm" ? 30 : 38} />
      <div className={`font-display font-bold leading-none ${size === "sm" ? "text-lg" : "text-xl"}`}>
        <span className="text-slate-900">Job</span><span className="text-brand-600">smith</span>
      </div>
    </div>
  )
}
