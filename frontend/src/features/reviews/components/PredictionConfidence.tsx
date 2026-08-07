export function PredictionConfidence({ value }: { value: number | null }) {
  if (value === null) return <span>Not available</span>;
  return <span>{new Intl.NumberFormat(undefined, { style: "percent", maximumFractionDigits: 1 }).format(value)}</span>;
}
