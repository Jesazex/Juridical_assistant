import type {
  AssistantApi,
  Chat,
  DocumentPage,
  Id,
  Message,
  MessageExchange,
} from "../api/types";
import { SEEDED_QUESTION, DOCUMENTS, findDocument, scriptedAnswer } from "./fixtures";

const STORAGE_KEY = "juridical-assistant-demo";

interface StoredChat extends Chat {
  titled: boolean;
}

interface Database {
  seq: number;
  chats: StoredChat[];
  messages: Message[];
}

const timers = new Set<number>();

function nowIso(): string {
  return new Date().toISOString();
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => {
    window.setTimeout(resolve, ms);
  });
}

function publicChat(chat: StoredChat): Chat {
  return {
    id: chat.id,
    title: chat.title,
    created_at: chat.created_at,
    updated_at: chat.updated_at,
  };
}

function titleFrom(content: string): string {
  const line = content.split("\n").map((part) => part.trim()).find(Boolean) ?? "Новый чат";
  return line.length > 72 ? `${line.slice(0, 71).trimEnd()}…` : line;
}

function seed(): Database {
  const created = nowIso();
  const question = SEEDED_QUESTION ?? "";
  const answer = scriptedAnswer(question);
  return {
    seq: 3,
    chats: [
      {
        id: 1,
        title: "Аренда «Северный Склад»",
        created_at: created,
        updated_at: created,
        titled: true,
      },
    ],
    messages: [
      {
        id: 1,
        chat_id: 1,
        role: "user",
        content: question,
        status: "completed",
        sources: [],
        created_at: created,
        updated_at: created,
      },
      {
        id: 2,
        chat_id: 1,
        role: "assistant",
        content: answer.content,
        status: "completed",
        sources: answer.sources,
        created_at: created,
        updated_at: created,
      },
    ],
  };
}

function revive(raw: unknown): Database {
  if (typeof raw !== "object" || raw === null) return seed();
  const record = raw as Partial<Database>;
  if (!Array.isArray(record.chats) || !Array.isArray(record.messages) || typeof record.seq !== "number") {
    return seed();
  }
  for (const message of record.messages) {
    if (message.status === "pending" && message.role === "assistant") {
      const user = [...record.messages]
        .reverse()
        .find(
          (item) =>
            item.chat_id === message.chat_id &&
            item.role === "user" &&
            item.created_at <= message.created_at &&
            String(item.id) !== String(message.id),
        );
      const answer = scriptedAnswer(user?.content ?? "");
      message.status = "completed";
      message.content = answer.content;
      message.sources = answer.sources;
    }
  }
  return record as Database;
}

function load(): Database {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return seed();
    return revive(JSON.parse(raw) as unknown);
  } catch {
    return seed();
  }
}

let database = load();

function save(): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(database));
}

export function clearDemo(): void {
  for (const timer of timers) window.clearTimeout(timer);
  timers.clear();
  sessionStorage.removeItem(STORAGE_KEY);
  database = seed();
  save();
}

function nextId(): number {
  const id = database.seq;
  database.seq += 1;
  return id;
}

function requireChat(id: Id): StoredChat {
  const chat = database.chats.find((item) => String(item.id) === String(id));
  if (!chat) throw Object.assign(new Error("Чат не найден или недоступен."), { status: 404 });
  return chat;
}

function pageOf<T>(items: T[], limit: number, offset: number) {
  return {
    items: items.slice(offset, offset + limit),
    total: items.length,
    limit,
    offset,
  };
}

function completeLater(messageId: Id, question: string): void {
  const timer = window.setTimeout(() => {
    timers.delete(timer);
    const message = database.messages.find((item) => String(item.id) === String(messageId));
    if (!message || message.status !== "pending") return;
    const answer = scriptedAnswer(question);
    message.status = "completed";
    message.content = answer.content;
    message.sources = answer.sources;
    message.updated_at = nowIso();
    save();
  }, 1100);
  timers.add(timer);
}

export const mockApi: AssistantApi = {
  async health() {
    return true;
  },

  async listChats(limit, offset) {
    await delay(80);
    const sorted = [...database.chats].sort((left, right) => {
      const byTime = right.updated_at.localeCompare(left.updated_at);
      if (byTime !== 0) return byTime;
      return String(right.id).localeCompare(String(left.id), "ru", { numeric: true });
    });
    return pageOf(sorted.map(publicChat), limit, offset);
  },

  async createChat(title) {
    await delay(80);
    const stamp = nowIso();
    const trimmed = title?.trim();
    const chat: StoredChat = {
      id: nextId(),
      title: trimmed || "Новый чат",
      created_at: stamp,
      updated_at: stamp,
      titled: Boolean(trimmed),
    };
    database.chats.push(chat);
    save();
    return publicChat(chat);
  },

  async renameChat(id, title) {
    await delay(60);
    const chat = requireChat(id);
    chat.title = title.trim();
    chat.titled = true;
    chat.updated_at = nowIso();
    save();
    return publicChat(chat);
  },

  async deleteChat(id) {
    await delay(60);
    requireChat(id);
    database.chats = database.chats.filter((item) => String(item.id) !== String(id));
    database.messages = database.messages.filter((item) => String(item.chat_id) !== String(id));
    save();
  },

  async listMessages(chatId, limit, offset) {
    await delay(40);
    requireChat(chatId);
    const items = database.messages
      .filter((item) => String(item.chat_id) === String(chatId))
      .sort(
        (left, right) =>
          left.created_at.localeCompare(right.created_at) ||
          String(left.id).localeCompare(String(right.id), "ru", { numeric: true }),
      );
    return pageOf(items, limit, offset);
  },

  async sendMessage(chatId, content): Promise<MessageExchange> {
    await delay(280);
    const chat = requireChat(chatId);
    const stamp = nowIso();
    const user: Message = {
      id: nextId(),
      chat_id: chat.id,
      role: "user",
      content,
      status: "completed",
      sources: [],
      created_at: stamp,
      updated_at: stamp,
    };
    const assistant: Message = {
      id: nextId(),
      chat_id: chat.id,
      role: "assistant",
      content: "",
      status: "pending",
      sources: [],
      created_at: stamp,
      updated_at: stamp,
    };
    database.messages.push(user, assistant);
    if (!chat.titled) {
      chat.title = titleFrom(content);
      chat.titled = true;
    }
    chat.updated_at = stamp;
    save();
    completeLater(assistant.id, content);
    return { user_message: user, assistant_message: assistant };
  },

  async retryMessage(chatId, messageId) {
    await delay(200);
    requireChat(chatId);
    const message = database.messages.find(
      (item) => String(item.id) === String(messageId) && String(item.chat_id) === String(chatId),
    );
    if (!message || message.role !== "assistant") {
      throw Object.assign(new Error("Не удалось повторить генерацию."), { status: 404 });
    }
    message.status = "pending";
    message.content = "";
    message.sources = [];
    message.error_code = null;
    message.updated_at = nowIso();
    const user = [...database.messages]
      .reverse()
      .find(
        (item) =>
          String(item.chat_id) === String(chatId) &&
          item.role === "user" &&
          item.created_at <= message.created_at &&
          String(item.id) !== String(message.id),
      );
    save();
    completeLater(message.id, user?.content ?? "");
    return { ...message };
  },

  async listDocuments(limit, offset): Promise<DocumentPage> {
    await delay(40);
    return pageOf(
      DOCUMENTS.map(({ id, title, group }) => ({ id, title, group })),
      limit,
      offset,
    );
  },

  async getDocument(id) {
    await delay(60);
    const document = findDocument(String(id));
    if (!document) throw Object.assign(new Error("Документ не найден."), { status: 404 });
    return document;
  },
};

if (import.meta.hot) {
  import.meta.hot.dispose(() => {
    for (const timer of timers) window.clearTimeout(timer);
  });
}
