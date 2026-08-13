/**
 * Minimal LLM client — OpenAI Chat Completions compatible.
 * ========================================================
 *
 * Reads LLM_API_URL / LLM_API_KEY / LLM_MODEL from import.meta.env.
 * Vite only exposes VITE_-prefixed vars to the browser, so vite.config.ts
 * re-exports the plain LLM_* names via `define` (see vite.config.ts).
 *
 * Contract: callLLM NEVER throws. It returns null when the API key is
 * empty, the request fails, or the response is malformed — callers fall
 * back to the rule engine.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface LLMOptions {
  /** Sampling temperature. Default 0.2 — deterministic enough for analysis. */
  temperature?: number;
  /** Max completion tokens (OpenAI-compatible `max_tokens`). */
  maxTokens?: number;
  /** Request JSON object output (`response_format: { type: "json_object" }`). */
  jsonMode?: boolean;
}

// ---------------------------------------------------------------------------
// Env access
// ---------------------------------------------------------------------------

function readEnv(name: string): string {
  const env = import.meta.env as unknown as Record<string, string | undefined>;
  return (env[name] ?? env[`VITE_${name}`] ?? "").trim();
}

/** True when an LLM API key is configured. Used by the Settings page. */
export function isLLMConfigured(): boolean {
  return readEnv("LLM_API_KEY") !== "";
}

// ---------------------------------------------------------------------------
// callLLM
// ---------------------------------------------------------------------------

/**
 * Call an OpenAI Chat Completions compatible endpoint.
 *
 * @param messages - Chat messages array, `[{ role, content }, ...]`.
 * @param options  - Optional temperature / max tokens / JSON mode.
 * @returns Assistant message text, or null when unavailable. Never throws.
 */
export async function callLLM(
  messages: ChatMessage[],
  options?: LLMOptions,
): Promise<string | null> {
  const url = readEnv("LLM_API_URL");
  const apiKey = readEnv("LLM_API_KEY");
  const model = readEnv("LLM_MODEL");

  if (!url || !apiKey) return null;

  // 30s timeout — slow analysis must not block the UI forever
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);

  try {
    const body: Record<string, unknown> = {
      messages,
      temperature: options?.temperature ?? 0.2,
    };
    if (model) body.model = model;
    if (options?.maxTokens != null) body.max_tokens = options.maxTokens;
    if (options?.jsonMode) body.response_format = { type: "json_object" };

    const res = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) return null;

    const json = (await res.json()) as {
      choices?: { message?: { content?: unknown } }[];
    };
    const content = json?.choices?.[0]?.message?.content;
    return typeof content === "string" ? content : null;
  } catch {
    // Network error, timeout, CORS, non-JSON body — all degrade to rules
    return null;
  } finally {
    clearTimeout(timer);
  }
}
