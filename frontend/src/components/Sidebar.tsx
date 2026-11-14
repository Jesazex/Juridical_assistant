import { useMemo, useState } from "react";
import type { Workspace } from "../hooks/useWorkspace";
import { formatListTime } from "../lib/text";
import { BrandMark, IconDoc, IconPlus, IconSearch, IconTrash } from "./Icons";

export function Sidebar({ workspace }: { workspace: Workspace }) {
  const [tab, setTab] = useState<"chats" | "docs">("chats");
  const [query, setQuery] = useState("");
  const documents = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return workspace.documents;
    return workspace.documents.filter((item) => item.title.toLowerCase().includes(needle));
  }, [query, workspace.documents]);
  const company = documents.filter((item) => item.group !== "law");
  const laws = documents.filter((item) => item.group === "law");
  const grouped = documents.some((item) => item.group);

  return (
    <aside className="sidebar">
      <div className="brand">
        <BrandMark />
        <div>
          <p className="brand__kicker">Внутренний контур</p>
          <h1 className="brand__title">Юридический ассистент</h1>
        </div>
      </div>

      <button className="new-chat" type="button" onClick={() => void workspace.createChat()}>
        <IconPlus />
        Новый вопрос
      </button>

      <div className="tabs" role="tablist" aria-label="Разделы">
        <button
          className="tabs__button"
          type="button"
          role="tab"
          aria-selected={tab === "chats"}
          onClick={() => setTab("chats")}
        >
          Чаты
        </button>
        <button
          className="tabs__button"
          type="button"
          role="tab"
          aria-selected={tab === "docs"}
          onClick={() => setTab("docs")}
        >
          База
        </button>
      </div>

      {tab === "chats" ? (
        <div className="sidebar__scroll" role="tabpanel">
          {workspace.chatsLoading ? <p className="sidebar__note">Загружаю чаты…</p> : null}
          {workspace.chatsError ? <p className="sidebar__note sidebar__note--warn">{workspace.chatsError}</p> : null}
          {!workspace.chatsLoading && workspace.chats.length === 0 ? (
            <p className="sidebar__note">Чатов пока нет. Новый вопрос откроет отдельную историю.</p>
          ) : null}
          <ul className="chat-list">
            {workspace.chats.map((chat) => {
              const active = String(chat.id) === String(workspace.activeId);
              return (
                <li key={chat.id}>
                  <div className={active ? "chat-item is-active" : "chat-item"}>
                    <button className="chat-item__open" type="button" onClick={() => void workspace.selectChat(chat.id)}>
                      <span className="chat-item__title">{chat.title}</span>
                      <span className="chat-item__time">{formatListTime(chat.updated_at)}</span>
                    </button>
                    <button
                      className="icon-button icon-button--ghost"
                      type="button"
                      aria-label={`Удалить чат «${chat.title}»`}
                      onClick={() => workspace.requestDelete(chat)}
                    >
                      <IconTrash size={16} />
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
          {workspace.chats.length < workspace.chatTotal ? (
            <button className="text-button" type="button" onClick={() => void workspace.loadMoreChats()}>
              Показать более ранние чаты
            </button>
          ) : null}
        </div>
      ) : (
        <div className="sidebar__scroll" role="tabpanel">
          <label className="search">
            <IconSearch size={16} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Название документа"
              aria-label="Поиск по названию документа"
            />
          </label>
          {workspace.documentsNote ? <p className="sidebar__note">{workspace.documentsNote}</p> : null}
          {grouped ? (
            <>
              <DocumentGroup
                title="Документы компании"
                items={company}
                onOpen={(id) => void workspace.openDocument(null, id)}
              />
              <DocumentGroup
                title="Законодательство"
                items={laws}
                onOpen={(id) => void workspace.openDocument(null, id)}
              />
            </>
          ) : (
            <DocumentGroup title="Документы" items={documents} onOpen={(id) => void workspace.openDocument(null, id)} />
          )}
          {documents.length === 0 && !workspace.documentsNote ? (
            <p className="sidebar__note">По этому запросу документов нет.</p>
          ) : null}
        </div>
      )}

      <footer className="sidebar__footer">
        <span className={workspace.health === "ok" ? "status-dot is-ok" : "status-dot"} />
        {workspace.mockMode ? "Демонстрационные ответы" : workspace.health === "ok" ? "API доступен" : "API недоступен"}
      </footer>
    </aside>
  );
}

function DocumentGroup({
  title,
  items,
  onOpen,
}: {
  title: string;
  items: Workspace["documents"];
  onOpen: (id: Workspace["documents"][number]["id"]) => void;
}) {
  if (items.length === 0) return null;
  return (
    <section className="doc-group">
      <h2>{title}</h2>
      <ul>
        {items.map((item) => (
          <li key={item.id}>
            <button type="button" onClick={() => onOpen(item.id)}>
              <IconDoc size={16} />
              <span>{item.title}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
