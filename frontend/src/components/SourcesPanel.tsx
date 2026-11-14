import type { Workspace } from "../hooks/useWorkspace";
import { safeHttpUrl } from "../lib/text";
import { IconClose } from "./Icons";

export function SourcesPanel({ workspace }: { workspace: Workspace }) {
  const message = workspace.sourceMessage;
  const sources = message?.sources ?? [];

  return (
    <aside className="sources" aria-label="Фрагменты ответа">
      <header className="sources__head">
        <div>
          <p className="brand__kicker">Основания</p>
          <h2>Фрагменты ответа</h2>
        </div>
        <button className="icon-button icon-button--overlay" type="button" aria-label="Закрыть фрагменты" onClick={() => workspace.setSourcesOpen(false)}>
          <IconClose />
        </button>
      </header>

      {!message || message.status === "pending" ? (
        <p className="sources__empty">Фрагменты появятся вместе с ответом.</p>
      ) : null}

      {message && message.status === "failed" ? (
        <p className="sources__empty">У этого ответа нет фрагментов: генерация не завершилась.</p>
      ) : null}

      {message && message.status === "completed" && sources.length === 0 ? (
        <div className="sources__empty">
          <p>К ответу не приложены цитаты из базы.</p>
          <p>Если данных недостаточно, ассистент пишет об этом в тексте ответа.</p>
        </div>
      ) : null}

      <ol className="source-list">
        {sources.map((source, index) => {
          const href = safeHttpUrl(source.url);
          const title = source.document_title || "Документ базы знаний";
          return (
            <li key={`${source.chunk_id ?? source.document_id ?? "source"}-${index}`}>
              <article className="source-card">
                <p className="source-card__index">{index + 1}</p>
                <h3>{title}</h3>
                <p className="source-card__meta">
                  {[source.section, source.page ? `стр. ${source.page}` : null].filter(Boolean).join(" · ") || "Фрагмент"}
                </p>
                {source.excerpt ? <blockquote>{source.excerpt}</blockquote> : <p className="source-card__meta">Текст фрагмента не передан.</p>}
                <div className="source-card__actions">
                  <button type="button" onClick={() => void workspace.openDocument(source)}>
                    Открыть документ
                  </button>
                  {href ? (
                    <a href={href} target="_blank" rel="noreferrer noopener">
                      Первоисточник
                    </a>
                  ) : null}
                </div>
              </article>
            </li>
          );
        })}
      </ol>
      <p className="sources__foot">Сверьте формулировку с полным текстом документа.</p>
    </aside>
  );
}
