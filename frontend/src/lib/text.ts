import type { Id, Message } from "../api/types";

export const MESSAGE_LIMIT = 10_000;
export const TITLE_LIMIT = 100;

export function fragmentLabel(count: number): string {
  const mod10 = count % 10;
  const mod100 = count % 100;
  const noun =
    mod10 === 1 && mod100 !== 11
      ? "фрагмент"
      : mod10 >= 2 && mod10 <= 4 && (mod100 < 12 || mod100 > 14)
        ? "фрагмента"
        : "фрагментов";
  return `${count} ${noun}`;
}

export function sameId(left: Id | null | undefined, right: Id | null | undefined): boolean {
  return left != null && right != null && String(left) === String(right);
}

export function parseApiDate(value: string): Date {
  const hasZone = /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  return new Date(hasZone ? value : `${value}Z`);
}

export function formatStamp(value: string): string {
  const date = parseApiDate(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  const time = new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(date);
  const sameDay = date.toDateString() === now.toDateString();
  if (sameDay) return `сегодня, ${time}`;
  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return `вчера, ${time}`;
  const day = new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "long" }).format(date);
  return `${day}, ${time}`;
}

export function formatListTime(value: string): string {
  const date = parseApiDate(value);
  if (Number.isNaN(date.getTime())) return "";
  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return new Intl.DateTimeFormat("ru-RU", { hour: "2-digit", minute: "2-digit" }).format(date);
  }
  return new Intl.DateTimeFormat("ru-RU", { day: "numeric", month: "short" }).format(date);
}

export function compareMessages(left: Message, right: Message): number {
  const byTime = left.created_at.localeCompare(right.created_at);
  if (byTime !== 0) return byTime;
  return String(left.id).localeCompare(String(right.id), "ru", { numeric: true });
}

export function mergeMessages(current: Message[], incoming: Message[]): Message[] {
  const map = new Map<string, Message>();
  for (const message of current) map.set(String(message.id), message);
  for (const message of incoming) map.set(String(message.id), message);
  return [...map.values()].sort(compareMessages);
}

export function locateExcerpt(text: string, excerpt: string): { start: number; end: number } | null {
  const needle = excerpt.trim();
  if (!needle) return null;
  const exact = text.indexOf(needle);
  if (exact >= 0) return { start: exact, end: exact + needle.length };

  let normalized = "";
  const map: number[] = [];
  let previousSpace = true;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index] ?? "";
    if (/\s/.test(char)) {
      if (!previousSpace) {
        normalized += " ";
        map.push(index);
        previousSpace = true;
      }
      continue;
    }
    normalized += char;
    map.push(index);
    previousSpace = false;
  }
  const target = needle.replace(/\s+/g, " ").trim();
  const at = normalized.indexOf(target);
  if (at < 0 || target.length === 0) return null;
  const start = map[at];
  const end = map[at + target.length - 1];
  if (start == null || end == null) return null;
  return { start, end: end + 1 };
}

export function safeHttpUrl(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    if (url.protocol === "http:" || url.protocol === "https:") return url.toString();
  } catch {
    return null;
  }
  return null;
}

export function failureCopy(code: string | null | undefined): string {
  if (code === "timeout") return "Генерация заняла слишком много времени.";
  if (code === "llm_unavailable") return "Языковая модель сейчас недоступна.";
  return "Ответ не сформирован. Повторная генерация использует уже отправленный вопрос.";
}
