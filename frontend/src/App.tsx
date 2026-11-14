import { ChatPane } from "./components/ChatPane";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { DocumentDialog } from "./components/DocumentDialog";
import { Sidebar } from "./components/Sidebar";
import { SourcesPanel } from "./components/SourcesPanel";
import { useWorkspaceState } from "./hooks/useWorkspace";
import { useMedia } from "./lib/useMedia";

export function App() {
  const workspace = useWorkspaceState();
  const wideNav = useMedia("(min-width: 801px)");
  const wideSources = useMedia("(min-width: 1081px)");
  const showBackdrop = (workspace.navOpen && !wideNav) || (workspace.sourcesOpen && !wideSources);
  const className = [
    "app",
    workspace.navOpen ? "is-nav-open" : "",
    workspace.sourcesOpen ? "is-sources-open" : "",
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <div className={className}>
      <a className="skip" href="#composer">
        К полю вопроса
      </a>
      {workspace.mockMode ? (
        <div className="demo-banner">
          <p>Демонстрация интерфейса: ответы взяты из примеров кейса, модель не вызывается.</p>
          <button
            type="button"
            onClick={() => {
              void import("./dev/mockApi").then(({ clearDemo }) => {
                clearDemo();
                window.location.reload();
              });
            }}
          >
            Сбросить демо
          </button>
        </div>
      ) : null}
      <div className="workspace">
        <Sidebar workspace={workspace} />
        <ChatPane workspace={workspace} />
        <SourcesPanel workspace={workspace} />
        {showBackdrop ? (
          <button
            className="backdrop"
            type="button"
            aria-label="Закрыть панель"
            onClick={() => {
              workspace.setNavOpen(false);
              if (!wideSources) workspace.setSourcesOpen(false);
            }}
          />
        ) : null}
      </div>
      {workspace.opened ? <DocumentDialog opened={workspace.opened} onClose={workspace.closeDocument} /> : null}
      {workspace.deleteTarget ? (
        <ConfirmDialog
          chat={workspace.deleteTarget}
          onCancel={workspace.cancelDelete}
          onConfirm={() => void workspace.confirmDelete()}
        />
      ) : null}
      <div className="sr-only" aria-live="polite">
        {workspace.announcement}
      </div>
    </div>
  );
}
