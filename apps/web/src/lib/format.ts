/** Business dates use UTC formatting so a timezone never shifts a source calendar day. */
export function formatDate(value: string | null | undefined): string {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "Not available";
  const date = new Date(`${value}T00:00:00Z`);
  if (
    !Number.isFinite(date.valueOf()) ||
    date.toISOString().slice(0, 10) !== value
  )
    return "Not available";
  return new Intl.DateTimeFormat("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(date);
}

/** Counts use a consistent English grouping convention; missing counts remain unavailable. */
export function formatCount(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value)
    ? "Not available"
    : new Intl.NumberFormat("en-GB", { maximumFractionDigits: 0 }).format(
        value,
      );
}

/** Currency is opt-in: Rossmann's unconfirmed source unit must never acquire an invented symbol. */
export function formatSales(value: number | null, currency?: string): string {
  if (value == null || !Number.isFinite(value)) return "Not available";
  const amount = new Intl.NumberFormat(
    "en-GB",
    currency
      ? {
          style: "currency",
          currency,
          minimumFractionDigits: 2,
          maximumFractionDigits: 2,
        }
      : { minimumFractionDigits: 2, maximumFractionDigits: 2 },
  ).format(value);
  return currency ? amount : `${amount} Sales units`;
}
