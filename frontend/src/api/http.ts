import {
  ApiError,
  type AssistantApi,
  type Chat,
  type ChatPage,
  type DocumentDetail,
  type DocumentPage,
  type DocumentSummary,
  type Id,
  type Message,
  type MessageExchange,
  type MessagePage,
  type MessageStatus,
  type Source,
} from "./types";

const API_ROOT = "/api/v1";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isId(value: unknown): value is Id {
  return typeof value === "number" || typeof value === "string";
}

function normalizeSource(value: unknown): Source | null {
  if (!isRecord(value)) return null;
  const source: Source = {
    document_id: isId(value.document_id) ? value.document_id : null,
    version_id: isId(value.version_id) ? value.version_id : null,
    document_title: typeof value.document_title === "string" ? value.document_title : null,
    chunk_id: isId(value.chunk_id) ? value.chunk_id : null,
    page: typeof value.page === "number" ? value.page : null,
    excerpt: typeof value.excerpt === "string" ? value.excerpt : null,
    url: typeof value.url === "string" ? value.url : null,
    section: typeof value.section === "string" ? value.section : null,
  };
  if (!source.document_title && !source.excerpt && source.document_id == null) return null;
  return source;
}

function normalizeStatus(value: unknown, role: Message["role"]): MessageStatus {
  if (value === "pending" || value === "completed" || value === "failed") return value;
  return role === "assistant" ? "completed" : "completed";
}

function normalizeMessage(value: unknown): Message | null {
  if (!isRecord(value) || !isId(value.id) || !isId(value.chat_id)) return null;
  if (value.role !== "user" && value.role !== "assistant") return null;
  if (typeof value.content !== "string") return null;
  const now = new Date().toISOString();
  return {
    id: value.id,
    chat_id: value.chat_id,
    role: value.role,
    content: value.content,
    status: normalizeStatus(value.status, value.role),
    sources: Array.isArray(value.sources)
      ? value.sources.map(normalizeSource).filter((item): item is Source => item !== null)
      : [],
    created_at: typeof value.created_at === "string" ? value.created_at : now,
    updated_at: typeof value.updated_at === "string" ? value.updated_at : now,
    error_code: typeof value.error_code === "string" ? value.error_code : null,
  };
}

function normalizeChat(value: unknown): Chat | null {
  if (!isRecord(value) || !isId(value.id)) return null;
  if (typeof value.title !== "string") return null;
  if (typeof value.created_at !== "string" || typeof value.updated_at !== "string") return null;
  return {
    id: value.id,
    title: value.title,
    created_at: value.created_at,
    updated_at: value.updated_at,
  };
}

function normalizeGroup(value: unknown): DocumentSummary["group"] {
  return value === "company" || value === "law" ? value : undefined;
}

function normalizeDocumentSummary(value: unknown): DocumentSummary | null {
  if (!isRecord(value) || !isId(value.id) || typeof value.title !== "string") return null;
  return { id: value.id, title: value.title, group: normalizeGroup(value.group) };
}

function normalizePage<T>(
  value: unknown,
  readItem: (item: unknown) => T | null,
): { items: T[]; total: number; limit: number; offset: number } | null {
  if (!isRecord(value) || !Array.isArray(value.items)) return null;
  const items = value.items.map(readItem).filter((item): item is T => item !== null);
  return {
    items,
    total: typeof value.total === "number" ? value.total : items.length,
    limit: typeof value.limit === "number" ? value.limit : items.length,
    offset: typeof value.offset === "number" ? value.offset : 0,
  };
}

async function errorFrom(response: Response, fallback: string): Promise<ApiError> {
  if (response.status === 404) return new ApiError(404, fallback);
  if (response.status === 422) {
    return new ApiError(422, "Проверьте текст: поле пустое или длиннее допустимого лимита.");
  }
  if (response.status === 429) return new ApiError(429, "Слишком много запросов. Подождите немного.");
  if (response.status >= 500) return new ApiError(response.status, "Сервис временно не отвечает.");
  return new ApiError(response.status, "Запрос не выполнен.");
}

async function request(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (init.body != null) headers.set("Content-Type", "application/json");
  try {
    return await fetch(`${API_ROOT}${path}`, {
      ...init,
      headers,
      credentials: "include",
    });
  } catch {
    throw new ApiError(0, "Нет соединения с сервером.");
  }
}

async function readJson(response: Response, fallback: string): Promise<unknown> {
  if (!response.ok) throw await errorFrom(response, fallback);
  if (response.status === 204) return null;
  return response.json() as Promise<unknown>;
}

function query(limit: number, offset: number): string {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return params.toString();
}

export const httpApi: AssistantApi = {
  async health() {
    const response = await request("/health");
    if (!response.ok) return false;
    const body = (await response.json()) as unknown;
    return isRecord(body) && body.status === "ok";
  },

  async listChats(limit, offset) {
    const body = await readJson(await request(`/chats/?${query(limit, offset)}`), "Не удалось загрузить чаты.");
    const page = normalizePage(body, normalizeChat);
    if (!page) throw new ApiError(500, "Сервер вернул список чатов в неожиданном формате.");
    return page satisfies ChatPage;
  },

  async createChat(title) {
    const payload = title ? { title } : {};
    const body = await readJson(
      await request("/chats/", { method: "POST", body: JSON.stringify(payload) }),
      "Не удалось создать чат.",
    );
    const chat = normalizeChat(body);
    if (!chat) throw new ApiError(500, "Сервер вернул чат в неожиданном формате.");
    return chat;
  },

  async renameChat(id, title) {
    const body = await readJson(
      await request(`/chats/${id}`, { method: "PATCH", body: JSON.stringify({ title }) }),
      "Чат не найден или недоступен.",
    );
    const chat = normalizeChat(body);
    if (!chat) throw new ApiError(500, "Сервер вернул чат в неожиданном формате.");
    return chat;
  },

  async deleteChat(id) {
    await readJson(await request(`/chats/${id}`, { method: "DELETE" }), "Чат не найден или недоступен.");
  },

  async listMessages(chatId, limit, offset) {
    const body = await readJson(
      await request(`/chats/${chatId}/messages/?${query(limit, offset)}`),
      "История чата недоступна.",
    );
    const page = normalizePage(body, normalizeMessage);
    if (!page) throw new ApiError(500, "Сервер вернул историю в неожиданном формате.");
    return page satisfies MessagePage;
  },

  async sendMessage(chatId, content) {
    const body = await readJson(
      await request(`/chats/${chatId}/messages/`, {
        method: "POST",
        body: JSON.stringify({ content }),
      }),
      "Чат не найден или недоступен.",
    );
    if (!isRecord(body)) throw new ApiError(500, "Сервер вернул ответ в неожиданном формате.");
    const user = normalizeMessage(body.user_message);
    const assistant = normalizeMessage(body.assistant_message);
    if (!user || !assistant) throw new ApiError(500, "Сервер вернул ответ в неожиданном формате.");
    return { user_message: user, assistant_message: assistant } satisfies MessageExchange;
  },

  async retryMessage(chatId, messageId) {
    const body = await readJson(
      await request(`/chats/${chatId}/messages/${messageId}/retry`, { method: "POST" }),
      "Не удалось повторить генерацию.",
    );
    const direct = normalizeMessage(body);
    if (direct) return direct;
    if (isRecord(body)) {
      const nested = normalizeMessage(body.assistant_message);
      if (nested) return nested;
    }
    throw new ApiError(500, "Сервер вернул ответ в неожиданном формате.");
  },

  async listDocuments(limit, offset) {
    const body = await readJson(
      await request(`/documents/?${query(limit, offset)}`),
      "Список документов пока недоступен.",
    );
    const page = normalizePage(body, normalizeDocumentSummary);
    if (!page) throw new ApiError(500, "Сервер вернул список документов в неожиданном формате.");
    return page satisfies DocumentPage;
  },

  async getDocument(id, versionId) {
    const path = versionId == null
      ? `/documents/${encodeURIComponent(id)}`
      : `/documents/${encodeURIComponent(id)}/versions/${encodeURIComponent(versionId)}`;
    const body = await readJson(await request(path), "Документ не найден.");
    if (!isRecord(body) || !isId(body.id) || typeof body.title !== "string") {
      throw new ApiError(500, "Сервер вернул документ в неожиданном формате.");
    }
    const text = typeof body.text === "string" ? body.text : typeof body.content === "string" ? body.content : null;
    return {
      id: body.id,
      title: body.title,
      text,
      group: normalizeGroup(body.group),
      version_id: isId(body.version_id) ? body.version_id : null,
      version_label: typeof body.version_label === "string" ? body.version_label : null,
      selected_version_id: isId(body.selected_version_id) ? body.selected_version_id : null,
      versions: Array.isArray(body.versions) ? body.versions.flatMap((version) =>
        isRecord(version) && isId(version.id) && typeof version.version_label === "string"
          ? [{ id: version.id, version_label: version.version_label }]
          : [],
      ) : [],
    } satisfies DocumentDetail;
  },
};
