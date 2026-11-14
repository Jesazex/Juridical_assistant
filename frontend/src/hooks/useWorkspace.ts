import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError, mockMode, type Chat, type DocumentDetail, type DocumentSummary, type Id, type Message, type Source } from "../api";
import { mergeMessages, sameId, TITLE_LIMIT } from "../lib/text";

export interface OpenDocument {
  source: Source | null;
  doc: DocumentDetail | null;
  loading: boolean;
  error: string | null;
}

function describe(error: unknown, fallback: string): string {
  return error instanceof ApiError ? error.message : error instanceof Error ? error.message : fallback;
}

export function useWorkspaceState() {
  const [chats, setChats] = useState<Chat[]>([]);
  const [chatTotal, setChatTotal] = useState(0);
  const [chatsLoading, setChatsLoading] = useState(true);
  const [chatsError, setChatsError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<Id | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [messageTotal, setMessageTotal] = useState(0);
  const [messageOffset, setMessageOffset] = useState(0);
  const [messagesLoading, setMessagesLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [banner, setBanner] = useState<string | null>(null);
  const [health, setHealth] = useState<"unknown" | "ok" | "down">("unknown");
  const [documents, setDocuments] = useState<DocumentSummary[]>([]);
  const [documentsNote, setDocumentsNote] = useState<string | null>(null);
  const [sourceMessageId, setSourceMessageId] = useState<Id | null>(null);
  const [opened, setOpened] = useState<OpenDocument | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Chat | null>(null);
  const [composerNonce, setComposerNonce] = useState(0);
  const [navOpen, setNavOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(
    () => window.matchMedia("(min-width: 1081px)").matches,
  );
  const [announcement, setAnnouncement] = useState("");
  const requestSeq = useRef(0);
  const documentRequestSeq = useRef(0);
  const activeIdRef = useRef<Id | null>(null);
  activeIdRef.current = activeId;

  const refreshChats = useCallback(async (prefer: number) => {
    const limit = Math.min(Math.max(prefer, 20), 100);
    const page = await api.listChats(limit, 0);
    setChats(page.items);
    setChatTotal(page.total);
    return page;
  }, []);

  const loadChat = useCallback(async (id: Id) => {
    const seq = requestSeq.current + 1;
    requestSeq.current = seq;
    setActiveId(id);
    setMessagesLoading(true);
    setBanner(null);
    setNavOpen(false);
    try {
      const head = await api.listMessages(id, 50, 0);
      const page = head.total > head.items.length
        ? await api.listMessages(id, 50, Math.max(0, head.total - 50))
        : head;
      if (requestSeq.current !== seq) return;
      setMessages(page.items);
      setMessageTotal(page.total);
      setMessageOffset(page.offset);
      const lastAssistant = [...page.items].reverse().find((item) => item.role === "assistant");
      setSourceMessageId(lastAssistant?.id ?? null);
    } catch (error) {
      if (requestSeq.current !== seq) return;
      setMessages([]);
      setBanner(describe(error, "История чата недоступна."));
    } finally {
      if (requestSeq.current === seq) setMessagesLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [page, alive, docs] = await Promise.all([
          api.listChats(20, 0),
          api.health().catch(() => false),
          api.listDocuments(100, 0).catch((error: unknown) => {
            if (!cancelled) {
              setDocumentsNote(
                describe(error, "Каталог базы знаний появится, когда будет подключён API документов."),
              );
            }
            return null;
          }),
        ]);
        if (cancelled) return;
        setChats(page.items);
        setChatTotal(page.total);
        setHealth(alive ? "ok" : "down");
        if (docs) {
          setDocuments(docs.items);
          setDocumentsNote(docs.items.length === 0 ? "В каталоге пока нет документов." : null);
        }
        const first = page.items[0];
        if (first) await loadChat(first.id);
      } catch (error) {
        if (!cancelled) {
          setChatsError(describe(error, "Не удалось загрузить чаты."));
          setHealth("down");
        }
      } finally {
        if (!cancelled) setChatsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadChat]);

  const pendingKey = messages
    .filter((item) => item.role === "assistant" && item.status === "pending")
    .map((item) => String(item.id))
    .join(",");

  useEffect(() => {
    if (!activeId || !pendingKey) return;
    let cancelled = false;
    let failures = 0;
    const timer = window.setInterval(() => {
      void (async () => {
        try {
          const probe = await api.listMessages(activeId, 50, 0);
          const tail = probe.total > 50 ? await api.listMessages(activeId, 50, probe.total - 50) : probe;
          if (cancelled || !sameId(activeIdRef.current, activeId)) return;
          failures = 0;
          setMessages((current) => mergeMessages(current, tail.items));
          setMessageTotal(tail.total);
          if (
            tail.items.some(
              (item) =>
                item.role === "assistant" &&
                item.status === "completed" &&
                pendingKey.split(",").includes(String(item.id)),
            )
          ) {
            setAnnouncement("Ответ получен. Фрагменты можно открыть рядом с текстом.");
          }
        } catch {
          failures += 1;
          if (failures >= 4 && !cancelled) setBanner("Не удаётся обновить статус ответа.");
        }
      })();
    }, 800);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [activeId, pendingKey]);

  const activeChat = useMemo(
    () => chats.find((chat) => sameId(chat.id, activeId)) ?? null,
    [activeId, chats],
  );

  const sourceMessage = useMemo(() => {
    const selected = messages.find((item) => sameId(item.id, sourceMessageId) && item.role === "assistant");
    if (selected) return selected;
    return [...messages].reverse().find((item) => item.role === "assistant") ?? null;
  }, [messages, sourceMessageId]);

  const createChat = useCallback(async () => {
    setBanner(null);
    try {
      const chat = await api.createChat();
      setChats((current) => [chat, ...current.filter((item) => !sameId(item.id, chat.id))]);
      setChatTotal((total) => total + 1);
      requestSeq.current += 1;
      setActiveId(chat.id);
      setMessages([]);
      setMessageOffset(0);
      setMessageTotal(0);
      setSourceMessageId(null);
      setComposerNonce((value) => value + 1);
      setNavOpen(false);
      setAnnouncement("Новый чат создан.");
    } catch (error) {
      setBanner(describe(error, "Не удалось создать чат."));
    }
  }, []);

  const renameChat = useCallback(async (id: Id, title: string) => {
    const next = title.trim();
    if (!next || next.length > TITLE_LIMIT) {
      setBanner("Название чата — от 1 до 100 символов.");
      return false;
    }
    try {
      const chat = await api.renameChat(id, next);
      setChats((current) =>
        current
          .map((item) => (sameId(item.id, id) ? chat : item))
          .sort((left, right) => right.updated_at.localeCompare(left.updated_at)),
      );
      setAnnouncement("Название чата сохранено.");
      return true;
    } catch (error) {
      setBanner(describe(error, "Не удалось переименовать чат."));
      return false;
    }
  }, []);

  const confirmDelete = useCallback(async () => {
    const target = deleteTarget;
    if (!target) return;
    try {
      await api.deleteChat(target.id);
      const remaining = chats.filter((item) => !sameId(item.id, target.id));
      setChats(remaining);
      setChatTotal((total) => Math.max(0, total - 1));
      setDeleteTarget(null);
      setAnnouncement("Чат и его история удалены.");
      if (sameId(activeId, target.id)) {
        const next = remaining[0];
        if (next) await loadChat(next.id);
        else {
          requestSeq.current += 1;
          setActiveId(null);
          setMessages([]);
          setMessageTotal(0);
          setMessageOffset(0);
          setSourceMessageId(null);
        }
      }
    } catch (error) {
      setBanner(describe(error, "Не удалось удалить чат."));
      setDeleteTarget(null);
    }
  }, [activeId, chats, deleteTarget, loadChat]);

  const send = useCallback(async (raw: string) => {
    const content = raw.trim();
    if (!activeId || sending) return false;
    if (!content) {
      setBanner("Введите вопрос.");
      return false;
    }
    if (content.length > 10_000) {
      setBanner("Сообщение длиннее 10 000 символов.");
      return false;
    }
    setSending(true);
    setBanner(null);
    try {
      const exchange = await api.sendMessage(activeId, content);
      if (!sameId(activeIdRef.current, activeId)) return true;
      setMessages((current) => mergeMessages(current, [exchange.user_message, exchange.assistant_message]));
      setMessageTotal((total) => total + 2);
      setSourceMessageId(exchange.assistant_message.id);
      setAnnouncement("Вопрос отправлен. Идёт поиск по базе знаний.");
      void refreshChats(Math.max(chats.length, 20)).catch(() => undefined);
      return true;
    } catch (error) {
      setBanner(describe(error, "Не удалось отправить вопрос."));
      return false;
    } finally {
      setSending(false);
    }
  }, [activeId, chats.length, refreshChats, sending]);

  const createThenSend = useCallback(async (raw: string) => {
    const content = raw.trim();
    if (!content || sending || content.length > 10_000) return;
    setSending(true);
    setBanner(null);
    try {
      const chat = await api.createChat();
      setChats((current) => [chat, ...current.filter((item) => !sameId(item.id, chat.id))]);
      setChatTotal((total) => total + 1);
      requestSeq.current += 1;
      activeIdRef.current = chat.id;
      setActiveId(chat.id);
      setNavOpen(false);
      const exchange = await api.sendMessage(chat.id, content);
      if (!sameId(activeIdRef.current, chat.id)) return;
      setMessages([exchange.user_message, exchange.assistant_message]);
      setMessageOffset(0);
      setMessageTotal(2);
      setSourceMessageId(exchange.assistant_message.id);
      setSourcesOpen(true);
      setAnnouncement("Вопрос отправлен. Идёт поиск по базе знаний.");
      void refreshChats(Math.max(chats.length + 1, 20)).catch(() => undefined);
    } catch (error) {
      setBanner(describe(error, "Не удалось отправить вопрос."));
    } finally {
      setSending(false);
    }
  }, [chats.length, refreshChats, sending]);

  const retry = useCallback(async (message: Message) => {
    setBanner(null);
    setMessages((current) =>
      current.map((item) => (sameId(item.id, message.id) ? { ...item, status: "pending", content: "" } : item)),
    );
    try {
      const updated = await api.retryMessage(message.chat_id, message.id);
      setMessages((current) => mergeMessages(current, [updated]));
      setSourceMessageId(updated.id);
      setAnnouncement("Генерация запущена повторно по тому же вопросу.");
    } catch (error) {
      setMessages((current) =>
        current.map((item) => (sameId(item.id, message.id) ? { ...item, status: "failed" } : item)),
      );
      setBanner(describe(error, "Не удалось повторить генерацию."));
    }
  }, []);

  const loadMoreChats = useCallback(async () => {
    if (chats.length >= chatTotal) return;
    try {
      const page = await api.listChats(20, chats.length);
      setChats((current) => {
        const known = new Set(current.map((item) => String(item.id)));
        return [...current, ...page.items.filter((item) => !known.has(String(item.id)))];
      });
      setChatTotal(page.total);
    } catch (error) {
      setBanner(describe(error, "Не удалось загрузить остальные чаты."));
    }
  }, [chatTotal, chats.length]);

  const loadOlder = useCallback(async () => {
    if (!activeId || messageOffset <= 0 || messagesLoading) return;
    const nextOffset = Math.max(0, messageOffset - 50);
    setMessagesLoading(true);
    try {
      const page = await api.listMessages(activeId, messageOffset - nextOffset, nextOffset);
      setMessages((current) => mergeMessages(page.items, current));
      setMessageOffset(page.offset);
      setMessageTotal(page.total);
    } catch (error) {
      setBanner(describe(error, "Не удалось загрузить более ранние сообщения."));
    } finally {
      setMessagesLoading(false);
    }
  }, [activeId, messageOffset, messagesLoading]);

  const openDocument = useCallback(async (source: Source | null, documentId?: Id, versionId?: Id) => {
    const seq = ++documentRequestSeq.current;
    const id = documentId ?? source?.document_id ?? null;
    // Старый источник без версии показываем как snapshot, не подменяем текущей редакцией.
    if (id == null || (source && source.version_id == null && versionId == null && !mockMode)) {
      setOpened({
        source,
        loading: false,
        error: null,
        doc: {
          id: "excerpt",
          title: source?.document_title ?? "Фрагмент",
          text: source?.excerpt ?? null,
        },
      });
      return;
    }
    setOpened((current) => ({
      source,
      doc: !source && current?.doc?.id === id ? { ...current.doc, text: null } : null,
      loading: true, error: null,
    }));
    try {
      const doc = await api.getDocument(id, versionId ?? source?.version_id ?? undefined);
      if (seq !== documentRequestSeq.current) return;
      setOpened((current) => ({
        source, loading: false, error: null,
        doc: {
          ...doc,
          versions: versionId != null && current?.doc?.id === id ? current.doc.versions : doc.versions,
        },
      }));
    } catch (error) {
      if (seq !== documentRequestSeq.current) return;
      setOpened({
        source,
        loading: false,
        error: describe(error, "Полный текст документа сейчас недоступен."),
        doc: {
          id,
          title: source?.document_title ?? "Документ",
          text: null,
        },
      });
    }
  }, []);

  const selectMessage = useCallback((id: Id) => {
    setSourceMessageId(id);
    setSourcesOpen(true);
  }, []);

  const dismissBanner = useCallback(() => setBanner(null), []);
  const cancelDelete = useCallback(() => setDeleteTarget(null), []);
  const closeDocument = useCallback(() => {
    documentRequestSeq.current += 1;
    setOpened(null);
  }, []);

  return {
    mockMode,
    chats,
    chatTotal,
    chatsLoading,
    chatsError,
    activeChat,
    activeId,
    messages,
    messageTotal,
    messageOffset,
    messagesLoading,
    sending,
    banner,
    health,
    documents,
    documentsNote,
    sourceMessage,
    opened,
    deleteTarget,
    composerNonce,
    navOpen,
    sourcesOpen,
    announcement,
    dismissBanner,
    setNavOpen,
    setSourcesOpen,
    selectChat: loadChat,
    createChat,
    renameChat,
    requestDelete: setDeleteTarget,
    cancelDelete,
    confirmDelete,
    send,
    createThenSend,
    retry,
    loadMoreChats,
    loadOlder,
    selectMessage,
    openDocument,
    closeDocument,
  };
}

export type Workspace = ReturnType<typeof useWorkspaceState>;
