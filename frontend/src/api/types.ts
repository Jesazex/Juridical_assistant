export type Id = number | string;

export type MessageRole = "user" | "assistant";
export type MessageStatus = "pending" | "completed" | "failed";

export interface Chat {
  id: Id;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface ChatPage {
  items: Chat[];
  total: number;
  limit: number;
  offset: number;
}

/** Поля источника совпадают с контрактом ответа AI из manual и MessageSource. */
export interface Source {
  document_id?: Id | null;
  version_id?: Id | null;
  document_title?: string | null;
  chunk_id?: Id | null;
  page?: number | null;
  excerpt?: string | null;
  url?: string | null;
  section?: string | null;
}

export interface Message {
  id: Id;
  chat_id: Id;
  role: MessageRole;
  content: string;
  status: MessageStatus;
  sources: Source[];
  created_at: string;
  updated_at: string;
  error_code?: string | null;
}

export interface MessagePage {
  items: Message[];
  total: number;
  limit: number;
  offset: number;
}

export interface MessageExchange {
  user_message: Message;
  assistant_message: Message;
}

export interface DocumentSummary {
  id: Id;
  title: string;
  group?: "company" | "law";
}

export interface DocumentPage {
  items: DocumentSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface DocumentDetail {
  id: Id;
  title: string;
  text: string | null;
  group?: "company" | "law";
  version_id?: Id | null;
  version_label?: string | null;
  versions?: Array<{ id: Id; version_label: string }>;
  selected_version_id?: Id | null;
}

export interface AssistantApi {
  health(): Promise<boolean>;
  listChats(limit: number, offset: number): Promise<ChatPage>;
  createChat(title?: string): Promise<Chat>;
  renameChat(id: Id, title: string): Promise<Chat>;
  deleteChat(id: Id): Promise<void>;
  listMessages(chatId: Id, limit: number, offset: number): Promise<MessagePage>;
  sendMessage(chatId: Id, content: string): Promise<MessageExchange>;
  retryMessage(chatId: Id, messageId: Id): Promise<Message>;
  listDocuments(limit: number, offset: number): Promise<DocumentPage>;
  getDocument(id: Id, versionId?: Id): Promise<DocumentDetail>;
}

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}
