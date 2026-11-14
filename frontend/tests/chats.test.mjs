import assert from "node:assert/strict";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { build } from "esbuild";

const bundle = await build({
  entryPoints: [fileURLToPath(new URL("../src/api/http.ts", import.meta.url))],
  bundle: true, write: false, platform: "node", format: "esm",
});
const { httpApi } = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);
const chat = { id: "chat-id", title: "Новый чат", created_at: "2026-11-14T12:00:00Z", updated_at: "2026-11-14T12:00:00Z" };

test("empty chat posts {} to relative API with cookies and returns the created chat", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json(chat, { status: 201 }));
  assert.deepEqual(await httpApi.createChat(), chat);
  const [path, options] = fetch.mock.calls[0].arguments;
  assert.equal(path, "/api/v1/chats/");
  assert.equal(options.method, "POST");
  assert.equal(options.body, "{}");
  assert.equal(options.credentials, "include");
  assert.equal(options.headers.get("Content-Type"), "application/json");
});

test("named chat sends the title", async (t) => {
  const fetch = t.mock.method(globalThis, "fetch", async () => Response.json({ ...chat, title: "Named" }, { status: 201 }));
  assert.equal((await httpApi.createChat("Named")).title, "Named");
  assert.deepEqual(JSON.parse(fetch.mock.calls[0].arguments[1].body), { title: "Named" });
});

test("API rejection propagates a readable error to the workspace banner", async (t) => {
  t.mock.method(globalThis, "fetch", async () => Response.json({ detail: "Request origin is not allowed" }, { status: 403 }));
  await assert.rejects(httpApi.createChat(), (error) => error.status === 403 && error.message.length > 0);
});
