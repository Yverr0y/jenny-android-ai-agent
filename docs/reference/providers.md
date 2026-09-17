# Providers and models

How Jenny talks to an LLM: the two wire formats it speaks, how to add or change a provider, and what actually happens (and doesn't) when you do.

Jenny does not ship with any model. It is bring-your-own-key: you point it at an LLM endpoint you already have access to, and every request — and every dollar or token it costs — goes through your own account.

## There is no built-in catalog

Jenny does not maintain a list of "supported providers." A provider is just an entry you define yourself: a name you pick, a wire format, a credential, and an endpoint. Jenny never infers anything from the model name, the shape of the API key, or the base URL — whatever you configure is exactly what runs. This is why pasting the right API key against the wrong base URL, or the right base URL with a model ID from a different service, is the single most common first-run failure (see [Quick checks](#quick-checks)).

## The two formats

Every provider entry declares one `format`, and that field alone decides which backend code path handles the request:

| Format | Speaks | Default base URL | Typical services |
|---|---|---|---|
| `anthropic` | Claude via the Anthropic Messages API | `https://api.anthropic.com` | Anthropic direct, or any Anthropic-Messages-compatible proxy |
| `openai_compat` | OpenAI Chat Completions (and optionally the Responses API) | `https://api.openai.com/v1` | OpenAI, Groq, DeepSeek, Ollama, vLLM, OpenRouter, Together, Fireworks, and any other Chat-Completions-shaped endpoint |

These are the exact hints shown in the onboarding wizard's "Choose your provider format" step: **Anthropic Compatible** — "Claude models via Anthropic Messages API" — and **OpenAI Compatible** — "OpenAI, Groq, DeepSeek, Ollama, vLLM, OpenRouter, Together, Fireworks...". The same two choices reappear in Settings → API keys whenever you add or edit a provider.

Both default base URLs apply only when you leave the base URL field empty. Change it whenever the service isn't the default one — Groq, DeepSeek, OpenRouter, Together, Fireworks, or anything self-hosted all need their own `apiBase` under the `openai_compat` format.

## Managing providers

Providers live under Settings → **Model** → **API keys** (the same screen the onboarding wizard's "Connect your provider" step writes to). Each entry shown there has:

- **Name** — a free-form label (e.g. "My Claude"), not a service identifier. It's what other config, like model presets, refers to.
- **Format** — the `anthropic` / `openai_compat` choice above.
- **API Key** — shown masked, as a 4+4 character hint (first four and last four characters) once one is configured, never displayed in full again.
- **Base URL** — shown as `(default)` when left empty.

Actions available from this screen: **Add provider**, **Edit**, **Delete**. A few things worth knowing:

- Saving shows **"Provider saved"**; deleting asks **`Delete provider "{name}"?`** and then confirms **"Provider deleted"**.
- You cannot delete the last remaining provider (**"Cannot delete the last provider"**) — Jenny always needs at least one configured to keep the agent runnable.
- Both **Name** and **API Key** are required to save (**"Name and API Key are required"**).
- **Anything you change on this screen hot-reloads immediately** — which provider is active, the key, the base URL, the format, the CA certificate — with no app restart and no "requires restart" prompt. The gateway rebuilds the provider backend in place and swaps it into the running agent for the next turn. If you've read an older doc (or `providers.md`'s previous revision) claiming a provider switch needs a restart, that claim is false as of the current code.
- Up to and including **0.11.0** that was only true of the active provider, the model and the base URL. Saving a **CA certificate** or an **API key** on its own left the running agent using the client it had built at startup, so a correct CA could load the model list and still fail every chat message with `[SSL: CERTIFICATE_VERIFY_FAILED]` ([#12](https://github.com/flagdizero/jenny-android-ai-agent/issues/12)). On those versions, force-stop the app and reopen it after saving; the certificate on disk is already correct and is picked up at startup.
- `apiType`, and the advanced `extraHeaders` / `extraBody` / `extraQuery` fields described below, are **not exposed in Settings at all** — they only exist if you hand-edit `workspace/config.json`. Hand-editing `config.json` directly *does* require restarting the app for the change to take effect; only Settings changes hot-reload.

## Provider fields (`config.json`)

The full field set, only reachable by hand-editing `providers.providers[]` in `config.json`:

| Field | Required | Description |
|---|---|---|
| `name` | yes | Free-form identifier, referenced by `providers.default` and by any `modelPresets.<preset>.provider`. |
| `format` | yes | `"anthropic"` or `"openai_compat"`. The only field that picks the backend. |
| `apiKey` | yes | The gateway refuses to start a provider without one — see the exact error below. Local servers that don't check keys still need a placeholder like `"EMPTY"`. |
| `apiBase` | no | Full HTTP base URL, version path included where the service expects it (e.g. `/v1`). Omit to use the format's default. |
| `caBundle` | no | Path to a PEM certificate to trust on top of the default roots — for a server with a certificate signed by your own CA. Relative paths start at the workspace. Also editable in Settings. See [Self-signed certificates](#self-signed-certificates). |
| `apiType` | no, `openai_compat` only | `"auto"` (default), `"chat_completions"`, or `"responses"`. See [Chat Completions vs. Responses API](#chat-completions-vs-responses-api-openai_compat-only). Config-only — not in Settings. |
| `extraHeaders` / `extraBody` / `extraQuery` | no | Extra request headers, body fields, and query params merged into every request to this provider. Config-only. |

Keys may be written as camelCase or snake_case in the file; Jenny always writes camelCase back when it saves.

## Self-signed certificates

If your server's certificate is signed by a CA of your own, installing that CA on the phone
does nothing for Jenny. Her HTTP calls are made by the Python runtime bundled inside the APK,
and that runtime carries **its own** set of trusted roots; Android's system and user
certificate stores are never consulted. The symptom is
`[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate`.

Name the CA in the provider instead:

1. Get the PEM file into the workspace. Sending it to Jenny as a chat attachment puts it in
   `workspace/uploads/`; asking her to save the text you paste works too.
2. Settings → Model → API keys → Edit the provider → **CA certificate**, and enter the path
   (relative paths start at the workspace, so `uploads/ca.pem` is enough).

The trust is **added**, not swapped: the default roots stay in place, so a provider that also
talks to a publicly-signed host keeps working. The same trust is used by the model catalog
probe, so the model list loads too.

If the file is missing, unreadable, or isn't a certificate, Settings refuses the save and says
which path failed — Jenny never quietly falls back to her own bundle, because that would leave
you believing you're using your certificate when you aren't. The same check runs at startup: a
`caBundle` that has gone missing since (a wiped workspace, a restore from backup — the file
lives in the workspace, so it does travel in a backup) stops the provider from being built, and
the gateway starts in its "no provider configured" state with the reason in the log.

Disabling certificate verification is deliberately not offered.

## Choosing the active provider

Jenny picks the active provider in this order:

1. the entry whose `name` matches `providers.default`, if set;
2. otherwise the first entry in the `providers.providers` list;
3. otherwise startup / the next request fails with **"No provider configured"**.

## API keys are stored in plaintext

Every `apiKey` value sits in `workspace/config.json` as plain text. The only thing standing between that file and the rest of the world is Android's normal per-app sandbox — there is no separate encryption, keychain, or OS credential store involved.

This matters for one specific reason: the app's manifest sets `allowBackup="true"` with no backup-exclusion rules. Android's automatic cloud backup (Google's built-in backup service) can therefore scoop up app data — including `config.json`, and with it every API key in plaintext — into the user's Google account backup. If you use Google's device backup, treat it as a place your API keys can end up, not just your device. <!-- TODO: verify on-device (O-9): what the auto-backup actually captures under targetSdk 34 without explicit dataExtractionRules --> There's a separate, deliberate encrypted backup for disaster recovery — see [Backup and restore](../using/backup.md) — but that's a different mechanism, and it does not change what `allowBackup` exposes to Google's own backup pipeline.

If you export an unencrypted copy of `config.json` yourself (e.g. by pulling it off the device for debugging), you are exporting your API keys in the clear; handle that file accordingly.

## Chat Completions vs. Responses API (`openai_compat` only)

`apiType: "auto"` (the default) mostly means "use Chat Completions." Jenny only considers the OpenAI Responses API at all when *both* of these are true:

- the base URL points directly at `api.openai.com` (not OpenRouter, not any other gateway), **and**
- the request either sets a `reasoningEffort` value, or the model is one of OpenAI's reasoning families (o1/o3/o4, or any `gpt-5*` model).

When both hold, Jenny tries the Responses API — and if it starts failing, a small circuit breaker kicks in: after **3 consecutive failures** for that model, it stops trying Responses and falls back to Chat Completions for **5 minutes** before probing Responses again (a single "half-open" retry). This is per-model, automatic, and not configurable beyond forcing `apiType` to `"chat_completions"` or `"responses"` explicitly if you want to skip the auto-detection entirely.

For every other endpoint — Groq, DeepSeek, Ollama, OpenRouter, a self-hosted server, anything that isn't `api.openai.com` directly — `auto` always means Chat Completions; the Responses API is never attempted.

That last sentence is about `auto` only. Setting `apiType: "responses"` **explicitly** forces the Responses API on any `openai_compat` base URL, auto-detection included — which is what makes gateways that serve a Responses-shaped endpoint of their own reachable (see [OpenCode Go](#opencode-go) below).

## Prompt caching: what's actually happening

Be precise about this, because it differs a lot by format:

- **`anthropic` format**: cache-control markers are always applied to every request. This is unconditional — no setting to flip.
- **`openai_compat` format**: Jenny only emits explicit `cache_control` markers when **both** the base URL is OpenRouter **and** the model name looks like a Claude/Anthropic model (contains "claude" or an `anthropic/` prefix). Every other `openai_compat` endpoint — OpenAI direct, Groq, DeepSeek, a self-hosted server, OpenRouter with a non-Claude model — gets no explicit cache markers from Jenny at all. Whatever caching happens there, if any, is entirely up to that provider's own server-side behavior; Jenny doesn't request or control it.

In short: don't expect Jenny-driven prompt caching outside of Anthropic-format requests and the OpenRouter-Claude combination specifically.

## OpenRouter attribution headers

When the configured base URL contains `openrouter` (case-insensitive), Jenny automatically attaches attribution headers to every request: an `HTTP-Referer` pointing at the project's GitHub repository and an `X-OpenRouter-Title` of "Jenny" (plus a categories header). This is fixed behavior tied to detecting an OpenRouter base URL — there's no setting to suppress it, and it has no effect on non-OpenRouter endpoints.

## OpenCode Go

[OpenCode Go](https://opencode.ai/docs/go/) is a subscription that fronts a curated set of open coding models behind one API key. Its docs ask third-party clients to identify themselves with their own user agent and to send a stable per-conversation ID in `x-opencode-session`, which the gateway uses for routing and prompt-cache affinity. Jenny does both automatically whenever the configured base URL contains `opencode.ai` — there's no setting to flip, and no effect on any other endpoint.

The conversation ID is a SHA-256 hash of Jenny's internal session key, truncated to 32 characters: opaque, stable for the life of a conversation, and distinct across conversations. The raw session key names a channel and a chat (`telegram:123456789`), so it is never sent as-is. Internal sessions — cron, Dream, heartbeat — each get their own ID, as does the unified user conversation. The model-catalog probe sends the user agent but no session header: a catalog listing is not a conversation.

### One base URL, three provider entries

Go serves the same base URL in three different wire formats, and a provider entry in Jenny picks exactly one. So reaching every model means up to three entries, all sharing `apiBase` and `apiKey`:

| `format` | `apiType` | Endpoint | Models |
|---|---|---|---|
| `openai_compat` | `chat_completions` | `/chat/completions` | GLM-5.x, Kimi, LongCat, DeepSeek, MiMo, Hy3/Hy4 |
| `openai_compat` | `responses` | `/responses` | Grok 4.6, GPT 5.6 Luna, Muse Spark |
| `anthropic` | — | `/messages` | MiniMax, Qwen3.x, Union Alpha |

Set `apiBase` to `https://opencode.ai/zen/go/v1` in all three: the `anthropic` format strips a trailing `/v1` before appending its own path, so one string works everywhere. Switching between model families means switching the active provider, not just the model field — a Go model ID sent to the wrong entry fails the way described under "Model IDs must match the endpoint exactly" below.

Settings only exposes name/format/API key/base URL, so `apiType: "responses"` has to be written into `workspace/config.json` by hand. Editing that provider from Settings afterwards preserves it.

### `name` is stripped from messages

The `/chat/completions` endpoint rejects the optional `name` key on a message instead of ignoring it, answering `messages[N]: "name" is not supported by this endpoint`. Jenny puts that key on tool-result messages, so the failure is late and looks worse than it is: the first request of a turn goes through, and the turn dies as soon as the model calls a tool. Jenny therefore drops `name` from outgoing messages when the base URL is OpenCode, and only then — every other endpoint still receives it. Nothing is lost: `tool_call_id` is what correlates a result with its call, and the local history keeps the name.

### Two things to know before subscribing

- **Privacy.** Most Go models are zero-retention, but `Muse Spark 1.2/1.3 Contributor` are not: their discounted pricing is explicitly in exchange for using your prompts and completions to train future models. For an agent with access to your files and messages, avoid them. `Grok 4.6` and `GPT 5.6 Luna` retain abuse-monitoring logs for 30 days.
- **Traffic shape.** Go is meant for coding agents and comparable clients, and the docs say traffic is monitored for abuse. Jenny's own validated-client peers include general-purpose agents, so its shape is fine, but the terms are OpenCode's to enforce and to change.

## Model IDs must match the endpoint exactly

Jenny sends whatever string you put in the model field straight to the provider. There's no translation or aliasing layer. The most common way a working provider config produces "model not found" is pointing a preset or the onboarding model field at a model ID that belongs to a different service than the one `apiBase`/`apiKey` are configured for — e.g. an OpenRouter-style `anthropic/claude-...` slug sent to a direct Anthropic endpoint, which expects a plain `claude-...` name (or vice versa).

## Quick checks

| Symptom | Likely cause |
|---|---|
| `Provider '<name>': api_key is required.` | The active provider entry has no `apiKey`. Local/self-hosted servers that ignore auth still need a placeholder value. |
| `messages[N]: "name" is not supported by this endpoint` (HTTP 400, after the first tool call) | An OpenCode base URL reached by a code path that skips the provider's message sanitiser. See [OpenCode Go](#name-is-stripped-from-messages). |
| `No provider configured. Add a provider in Settings or edit workspace/config.json...` | `providers.providers` is empty. Add one from Settings → Model → API keys, or by hand-editing `config.json`. |
| 401 / unauthorized | The key is missing, expired, has stray whitespace, or belongs to a different service than the configured base URL. |
| Model not found | The model ID doesn't exist on the endpoint you configured — check it's the exact ID that endpoint serves, not a name copied from a different provider's docs. |
| Connection refused | A local/self-hosted server isn't running, or the base URL has the wrong host, port, or path. See [Local models](./local-models.md) if the endpoint is off-device. |
| Could not fetch models | Settings' model picker probes the endpoint's model list and failed; this doesn't block saving a provider, it just means you'll need to type the model ID manually. |

The Settings model picker's probe (`GET <apiBase>/models`) is advisory only — a failed probe never blocks you from saving a provider or typing a model ID by hand, and a successful one never changes anything in your config beyond what you explicitly choose.

## See also

- [Local models](./local-models.md) — self-hosted endpoints (Ollama, vLLM, LM Studio) reachable from the phone.
- [Configuration](./configuration.md) — full `config.json` reference, including model presets and agent defaults.
- [Settings](./settings.md) — the Settings UI tour, including the Model section and Advanced parameters.
- [First run](../start/first-run.md) — the onboarding wizard that writes your first provider entry.
- [Privacy](../internals/privacy.md) — what leaves the device and when.
