import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { Workspace } from "../hooks/useWorkspace";
import { SUGGESTIONS } from "../lib/suggestions";
import { MESSAGE_LIMIT, failureCopy, formatStamp, fragmentLabel, sameId } from "../lib/text";
import { IconMenu, IconPanel, IconPencil, IconRetry } from "./Icons";

export function ChatPane({ workspace }: { workspace: Workspace }) {
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState("");
  const threadRef = useRef<HTMLDivElement>(null);
  const composerRef = useRef<HTMLTextAreaElement>(null);
  const stickRef = useRef(true);
  const previousHeight = useRef(0);
  const chat = workspace.activeChat;
  const trimmed = draft.trim();
  const overLimit = trimmed.length > MESSAGE_LIMIT;

  useEffect(() => {
    setEditing(false);
    setTitle(chat?.title ?? "");
    stickRef.current = true;
    previousHeight.current = 0;
  }, [chat?.id, chat?.title]);

  useEffect(() => {
    composerRef.current?.focus();
  }, [workspace.composerNonce]);

  useEffect(() => {
    const field = composerRef.current;
    if (!field) return;
    field.style.height = "0px";
    field.style.height = `${Math.min(field.scrollHeight, 220)}px`;
  }, [draft]);

  useEffect(() => {
    const thread = threadRef.current;
    if (!thread) return;
    if (previousHeight.current && thread.scrollHeight > previousHeight.current && !stickRef.current) {
      thread.scrollTop += thread.scrollHeight - previousHeight.current;
    } else if (stickRef.current) {
      thread.scrollTop = thread.scrollHeight;
    }
    previousHeight.current = thread.scrollHeight;
  }, [workspace.messages, workspace.sending, workspace.messagesLoading]);

  function onThreadScroll() {
    const thread = threadRef.current;
    if (!thread) return;
    stickRef.current = thread.scrollHeight - thread.scrollTop - thread.clientHeight < 80;
  }

  async function submit(text: string) {
    stickRef.current = true;
    const sent = await workspace.send(text);
    if (sent && text === draft) setDraft("");
  }

  function onKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault();
      void submit(draft);
    }
  }

  async function saveTitle() {
    if (!chat) return;
    const saved = await workspace.renameChat(chat.id, title);
    if (saved) setEditing(false);
  }

  return (
    <section className="chat" aria-label="Диалог">
      <header className="topbar">
        <button
          className="icon-button icon-button--menu"
          type="button"
          aria-label="Открыть список чатов"
          onClick={() => workspace.setNavOpen(true)}
        >
          <IconMenu />
        </button>
        <div className="topbar__title">
          {editing && chat ? (
            <form
              className="rename"
              onSubmit={(event) => {
                event.preventDefault();
                void saveTitle();
              }}
            >
              <label className="sr-only" htmlFor="chat-title">
                Название чата
              </label>
              <input
                id="chat-title"
                value={title}
                maxLength={100}
                onChange={(event) => setTitle(event.target.value)}
                autoFocus
              />
              <button className="text-button" type="submit">
                Сохранить
              </button>
              <button className="text-button" type="button" onClick={() => setEditing(false)}>
                Отмена
              </button>
            </form>
          ) : (
            <>
              <h2>{chat?.title ?? "Новый вопрос"}</h2>
              {chat ? (
                <button className="icon-button" type="button" aria-label="Переименовать чат" onClick={() => setEditing(true)}>
                  <IconPencil size={16} />
                </button>
              ) : null}
            </>
          )}
          <p>Ответ строится по базе знаний. Каждое положение можно открыть и сверить.</p>
        </div>
        <button
          className="icon-button"
          type="button"
          aria-label={workspace.sourcesOpen ? "Скрыть фрагменты" : "Показать фрагменты"}
          aria-pressed={workspace.sourcesOpen}
          onClick={() => workspace.setSourcesOpen(!workspace.sourcesOpen)}
        >
          <IconPanel />
        </button>
      </header>

      {workspace.banner ? (
        <div className="banner" role="status">
          <p>{workspace.banner}</p>
          <button type="button" onClick={workspace.dismissBanner}>
            Закрыть
          </button>
        </div>
      ) : null}

      <div className="thread" ref={threadRef} onScroll={onThreadScroll}>
        <div className="thread__inner">
          {workspace.messageOffset > 0 ? (
            <button className="text-button text-button--center" type="button" onClick={() => void workspace.loadOlder()}>
              {workspace.messagesLoading ? "Загружаю…" : "Более ранние сообщения"}
            </button>
          ) : null}

          {!chat && !workspace.chatsLoading ? (
            <EmptyState onCreate={() => void workspace.createChat()} onAsk={(text) => void workspace.createThenSend(text)} />
          ) : null}

          {chat && workspace.messages.length === 0 && !workspace.messagesLoading ? (
            <div className="empty">
              <p className="empty__kicker">С чего начать</p>
              <h3>Спросите о договоре, редакции или норме из базы.</h3>
              <div className="suggestions">
                {SUGGESTIONS.map((item) => (
                  <button key={item} type="button" onClick={() => void submit(item)}>
                    {item}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          <ol className="messages">
            {workspace.messages.map((message) => {
              const selected = message.role === "assistant" && sameId(message.id, workspace.sourceMessage?.id);
              return (
                <li key={message.id} className={message.role === "user" ? "message message--user" : "message"}>
                  {message.role === "user" ? (
                    <article>
                      <p className="message__role">Вы</p>
                      <p className="message__text">{message.content}</p>
                      <time dateTime={message.created_at}>{formatStamp(message.created_at)}</time>
                    </article>
                  ) : (
                    <article className={selected ? "memo is-selected" : "memo"}>
                      <div className="memo__meta">
                        <p className="message__role">Ассистент</p>
                        <StatusChip message={message} onOpen={() => workspace.selectMessage(message.id)} />
                      </div>
                      {message.status === "pending" ? (
                        <p className="memo__pending">Ищу положения в базе знаний и проверяю, достаточно ли их для ответа.</p>
                      ) : (
                        <p className="message__text message__text--serif">{message.content}</p>
                      )}
                      {message.status === "failed" ? <p className="memo__failed">{failureCopy(message.error_code)}</p> : null}
                      <footer>
                        <time dateTime={message.created_at}>{formatStamp(message.created_at)}</time>
                        {message.status === "failed" ? (
                          <button type="button" onClick={() => void workspace.retry(message)}>
                            <IconRetry size={15} />
                            Повторить генерацию
                          </button>
                        ) : null}
                        {message.status === "completed" && message.sources.length > 0 ? (
                          <button type="button" onClick={() => workspace.selectMessage(message.id)}>
                            Открыть {fragmentLabel(message.sources.length)}
                          </button>
                        ) : null}
                      </footer>
                    </article>
                  )}
                </li>
              );
            })}
          </ol>

          {workspace.sending ? <p className="memo__pending memo__pending--alone">Отправляю вопрос…</p> : null}
        </div>
      </div>

      <form
        className="composer"
        id="composer"
        onSubmit={(event) => {
          event.preventDefault();
          void submit(draft);
        }}
      >
        <label className="sr-only" htmlFor="question">
          Вопрос ассистенту
        </label>
        <textarea
          id="question"
          ref={composerRef}
          rows={1}
          value={draft}
          maxLength={MESSAGE_LIMIT}
          placeholder={chat ? "Уточните договор, контрагента, дату или норму" : "Сначала создайте чат"}
          disabled={!chat || workspace.sending}
          aria-describedby="composer-hint"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={onKeyDown}
        />
        <div className="composer__bar">
          <p id="composer-hint">
            Enter отправляет, Shift+Enter переносит строку. {trimmed.length.toLocaleString("ru-RU")} / {MESSAGE_LIMIT.toLocaleString("ru-RU")}
          </p>
          <button type="submit" disabled={!chat || workspace.sending || !trimmed || overLimit}>
            Спросить
          </button>
        </div>
      </form>
    </section>
  );
}

function StatusChip({
  message,
  onOpen,
}: {
  message: Workspace["messages"][number];
  onOpen: () => void;
}) {
  if (message.status === "pending") return <span className="chip">Поиск</span>;
  if (message.status === "failed") return <span className="chip chip--danger">Ошибка</span>;
  if (message.sources.length > 0) {
    return (
      <button className="chip chip--ok" type="button" onClick={onOpen}>
        Фрагменты: {message.sources.length}
      </button>
    );
  }
  return (
    <button className="chip" type="button" onClick={onOpen}>
      Без цитат
    </button>
  );
}

function EmptyState({ onCreate, onAsk }: { onCreate: () => void; onAsk: (text: string) => void }) {
  return (
    <div className="empty">
      <p className="empty__kicker">Рабочий стол юриста</p>
      <h3>Отдельный чат для каждого вопроса.</h3>
      <p className="empty__copy">
        История сохранится в этом браузере. Ассистент отвечает по документам базы и показывает фрагмент, на котором держится вывод.
      </p>
      <button className="new-chat new-chat--inline" type="button" onClick={onCreate}>
        Начать пустой чат
      </button>
      <div className="suggestions">
        {SUGGESTIONS.map((item) => (
          <button key={item} type="button" onClick={() => onAsk(item)}>
            {item}
          </button>
        ))}
      </div>
    </div>
  );
}
