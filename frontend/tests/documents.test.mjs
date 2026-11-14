import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/api/http.ts", import.meta.url))],
  bundle: true,
  write: false,
  platform: "node",
  format: "esm",
});
const { httpApi } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);

test("document sources retain the version returned by Message API", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({
    items: [{
      id: "answer", chat_id: "chat", role: "assistant", content: "Answer", status: "completed",
      sources: [{ document_id: "document", version_id: "historical", chunk_id: "chunk", document_title: "Law" }],
    }], total: 1, limit: 50, offset: 0,
  }));
  const page = await httpApi.listMessages("chat", 50, 0);
  assert.equal(page.items[0].sources[0].version_id, "historical");
  assert.equal(page.items[0].sources[0].document_id, "document");
});

test("explicit edition requests the version endpoint and preserves its text and label", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({
    id: "document", title: "Law", version_id: "historical", version_label: "Old edition", text: "Old text",
  }));
  const doc = await httpApi.getDocument("document", "historical");
  assert.equal(fetch.mock.calls[0].arguments[0], "/api/v1/documents/document/versions/historical");
  assert.equal(doc.version_id, "historical");
  assert.equal(doc.version_label, "Old edition");
  assert.equal(doc.text, "Old text");
});

test("ambiguous document keeps its editions and does not invent a text", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({
    id: "document", title: "Law", text: null, selected_version_id: null,
    versions: [{ id: "old", version_label: "Old" }, { id: "new", version_label: "New" }],
  }));
  const doc = await httpApi.getDocument("document");
  assert.equal(fetch.mock.calls[0].arguments[0], "/api/v1/documents/document");
  assert.equal(doc.text, null);
  assert.deepEqual(doc.versions.map((version) => version.id), ["old", "new"]);
});

test("unavailable historical edition reports 404 without falling back to current edition", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => new Response(null, { status: 404 }));
  await assert.rejects(httpApi.getDocument("document", "deleted"), (error) => error.status === 404);
  assert.equal(fetch.mock.callCount(), 1);
});
