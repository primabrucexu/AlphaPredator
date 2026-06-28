const EXPLICIT_TIME_ZONE_PATTERN = /(Z|[+-]\d{2}:?\d{2})$/i;

function formatPartsInBeijing(date: Date): string {
  const parts = new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(date);
  const byType = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  return `${byType.year}-${byType.month}-${byType.day} ${byType.hour}:${byType.minute}`;
}

function formatLocalIsoLike(value: string): string | null {
  const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/);
  if (!match) return null;
  return `${match[1]}-${match[2]}-${match[3]} ${match[4]}:${match[5]}`;
}

export function formatBeijingDateTime(value: string | null | undefined): string {
  const text = value?.trim();
  if (!text) return '-';

  if (!EXPLICIT_TIME_ZONE_PATTERN.test(text)) {
    return formatLocalIsoLike(text) ?? text;
  }

  const date = new Date(text);
  if (Number.isNaN(date.getTime())) {
    return text;
  }
  return formatPartsInBeijing(date);
}
