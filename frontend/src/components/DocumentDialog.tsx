import { useEffect, useRef } from "react";
import type { OpenDocument } from "../hooks/useWorkspace";
import { locateExcerpt, safeHttpUrl } from "../lib/text";
import { IconClose } from "./Icons";

export function DocumentDialog({
  opened,
  onClose,
}: {
  opened: OpenDocument;
  onClose: () => void;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  const source = opened.source;
  const text = opened.doc?.text ?? "";
  const spot = text && source?.excerpt ? locateExcerpt(text, source.excerpt) : null;
  const href = safeHttpUrl(source?.url);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    document.getElementById("excerpt-mark")?.scrollIntoView({ block: "center" });
  }, [opened.doc?.id, source?.excerpt]);

  return (
    <div className="dialog-layer" role="presentation">
      <button className="dialog-layer__backdrop" type="button" aria-label="Закрыть документ" onClick={onClose} />
      <section className="dialog" role="dialog" aria-modal="true" aria-labelledby="document-title">
        <header className="dialog__head">
          <div>
            <p className="brand__kicker">{source?.section || "Документ базы"}</p>
            <h2 id="document-title">{opened.doc?.title ?? source?.document_title ?? "Документ"}</h2>
          </div>
          <button ref={closeRef} className="icon-button" type="button" aria-label="Закрыть" onClick={onClose}>
            <IconClose />
          </button>
        </header>
        {opened.loading ? <p className="dialog__note">Загружаю текст…</p> : null}
        {opened.error ? <p className="dialog__note">{opened.error}</p> : null}
        {source?.excerpt ? (
          <blockquote className="dialog__excerpt">
            <p>{source.excerpt}</p>
          </blockquote>
        ) : null}
        {text ? (
          <div className="document-text">
            {spot ? (
              <>
                {text.slice(0, spot.start)}
                <mark id="excerpt-mark">{text.slice(spot.start, spot.end)}</mark>
                {text.slice(spot.end)}
              </>
            ) : (
              text
            )}
          </div>
        ) : !opened.loading ? (
          <p className="dialog__note">
            Полный текст этого документа в текущем ответе не загружен. Ориентируйтесь на фрагмент выше, если он есть.
          </p>
        ) : null}
        {href ? (
          <p className="dialog__link">
            <a href={href} target="_blank" rel="noreferrer noopener">
              Открыть первоисточник
            </a>
          </p>
        ) : null}
      </section>
    </div>
  );
}
