import { httpApi } from "./http";
import type { AssistantApi } from "./types";

export const mockMode = import.meta.env.VITE_USE_MOCK === "true";

export const api: AssistantApi = mockMode ? (await import("../dev/mockApi")).mockApi : httpApi;

export { ApiError } from "./types";
export type {
  Chat,
  ChatPage,
  DocumentDetail,
  DocumentSummary,
  Id,
  Message,
  Source,
} from "./types";
