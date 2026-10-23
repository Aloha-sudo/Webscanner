import { t } from '../i18n/core';
/**
 * Форматирует секунды в человекочитаемый вид:
 *   45   → "45s"
 *   95   → "1m 35s"
 *   3725 → "1h 2m 5s"
 */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || seconds < 0) return '—';
  const s = Math.floor(seconds);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const rs = s % 60;
  if (m < 60) return rs ? `${m}m ${rs}s` : `${m}m`;
  const h = Math.floor(m / 60);
  const rm = m % 60;
  return rm ? `${h}h ${rm}m` : `${h}h`;
}

/**
 * Короткое имя профиля для UI.
 */
export function profileLabel(scan: { scan_type: string; ports?: string | null }): string {
  switch (scan.scan_type) {
    case 'quick':   return t("Быстрый");
    case 'top100': return t("Топ 100");
    case 'top1000': return t("1000 портов");
    case 'web':     return t("Веб-порты");
    case 'full':    return t("Все порты");
    case 'custom':  return scan.ports ? t("Свои порты ({v0})", {
  v0: truncate(scan.ports, 30)
}) : t("Свои порты");
    default:        return scan.scan_type.startsWith('import-') ? t("Из файла · {v0}", {
  v0: scan.scan_type.slice(7)
}) : scan.scan_type;
  }
}

function truncate(s: string, n: number): string {
  return s.length > n ? s.slice(0, n - 1) + '…' : s;
}

export function stageLabel(stage: string): string {
  const stages: Record<string,string> = {queued:t("Ожидание worker"),starting:t("Подготовка"),rustscan:t("Поиск портов"),verifying:t("Проверка портов"),nmap:t("Определение сервисов"),parsing_nmap:t("Обработка результатов"),dns:t("Определение DNS-имён (до 60 секунд)"),httpx:t("Проверка веб-сервисов"),web_fallback:t("Дополнительная проверка HTTPS (до 2 минут)"),gowitness:t("Создание скриншотов"),completed:t("Завершено"),failed:t("Ошибка"),cancelled:t("Отменено"),imported:t("Загружен из файла")};
  return stages[stage] || stage;
}

export function speedLabel(speed: string | null | undefined): string {
  const labels: Record<string, string> = {normal:t("Обычная"),fast:t("Быстрая"),hard:t("Интенсивная")};
  return speed ? labels[speed] || t("Неизвестна") : t("Не указана");
}
