const sameYear = new Intl.DateTimeFormat("en", { month: "short", day: "numeric" })
const otherYear = new Intl.DateTimeFormat("en", { month: "short", day: "numeric", year: "numeric" })

/** "Sep 29", or "Sep 29, 2025" for other years. */
export function formatDate(iso: string): string {
  const date = new Date(iso)
  return (date.getFullYear() === new Date().getFullYear() ? sameYear : otherYear).format(date)
}

/** "Just now", "5 min ago", "3 h ago", "Yesterday", then a date. */
export function formatRelative(iso: string): string {
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000
  if (seconds < 60) return "Just now"
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`
  if (seconds < 172800) return "Yesterday"
  return formatDate(iso)
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** Plain-text preview of a Markdown summary (no **, #, bullets or headings). */
export function summaryPreview(markdown: string): string {
  return markdown
    .replace(/\*\*(Key points|Conclusion):?\*\*:?/gi, " ")
    .replace(/[*_`#>]/g, "")
    .replace(/^\s*[-•]\s+/gm, "")
    .replace(/\s+/g, " ")
    .trim()
}

export function pluralize(count: number, singular: string, plural = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : plural}`
}
