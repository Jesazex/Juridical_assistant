import { useEffect, useRef } from "react";
import type { Chat } from "../api";

export function ConfirmDialog({
  chat,
  onCancel,
  onConfirm,
}: {
  chat: Chat;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    cancelRef.current?.focus();
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="dialog-layer" role="presentation">
      <button className="dialog-layer__backdrop" type="button" aria-label="Оставить чат" onClick={onCancel} />
      <section className="dialog dialog--confirm" role="dialog" aria-modal="true" aria-labelledby="delete-title">
        <h2 id="delete-title">Удалить чат «{chat.title}»?</h2>
        <p>Вместе с чатом исчезнут сообщения и связанные с ним данные.</p>
        <div className="dialog__actions">
          <button ref={cancelRef} className="text-button" type="button" onClick={onCancel}>
            Оставить
          </button>
          <button className="danger-button" type="button" onClick={onConfirm}>
            Удалить чат
          </button>
        </div>
      </section>
    </div>
  );
}
