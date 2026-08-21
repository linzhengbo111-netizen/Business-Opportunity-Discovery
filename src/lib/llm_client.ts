/**
 * Minimal LLM client — OpenAI Chat Completions compatible.
 * ========================================================
 *
 * Calls go through the Cloudflare Worker proxy at POST /api/llm (see
 * api-worker.js). The API key lives worker-side as a secret — never in
 * the bundle. Direct browser calls to api.deepseek.com would be blocked
 * by CORS, which is why the proxy exists.
 *
 * Contract: callLLM NEVER throws. It returns null when the worker is
 * unreachable, the request fails, or the response is malformed — callers
 * fall back to the rule engine.
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
// Worker proxy
// ---------------------------------------------------------------------------

/**
 * True when the worker has an LLM API key configured (worker-side secret).
 * Async — checks GET /api/llm/status instead of reading build-time env.
 */
export async function isLLMConfigured(): Promise<boolean> {
  try {
    const res = await fetch("/api/llm/status");
    if (!res.ok) {
      console.warn(`[llm] GET /api/llm/status failed: HTTP ${res.status}`);
      return false;
    }
    const json = (await res.json()) as { configured?: boolean };
    return json?.configured === true;
  } catch (err) {
    console.warn("[llm] GET /api/llm/status unreachable:", err);
    return false;
  }
}

// ---------------------------------------------------------------------------
// callLLM
// ---------------------------------------------------------------------------

/**
 * Call an OpenAI Chat Completions compatible endpoint via the worker proxy.
 *
 * @param messages - Chat messages array, `[{ role, content }, ...]`.
 * @param options  - Optional temperature / max tokens / JSON mode.
 * @returns Assistant message text, or null when unavailable. Never throws.
 */
export async function callLLM(
  messages: ChatMessage[],
  options?: LLMOptions,
): Promise<string | null> {
  // 30s timeout — slow analysis must not block the UI forever
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);

  try {
    const body: Record<string, unknown> = {
      messages,
      temperature: options?.temperature ?? 0.2,
    };
    if (options?.maxTokens != null) body.max_tokens = options.maxTokens;
    if (options?.jsonMode) body.response_format = { type: "json_object" };

    const res = await fetch("/api/llm", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      signal: controller.signal,
    });

    if (!res.ok) {
      console.warn(`[llm] POST /api/llm failed: HTTP ${res.status}`);
      return null;
    }

    const json = (await res.json()) as {
      choices?: { message?: { content?: unknown } }[];
    };
    const content = json?.choices?.[0]?.message?.content;
    if (typeof content !== "string") {
      console.warn("[llm] POST /api/llm: malformed response body");
      return null;
    }
    return content;
  } catch (err) {
    // Network error, timeout, worker down, non-JSON body — all degrade to rules
    console.warn("[llm] POST /api/llm failed:", err);
    return null;
  } finally {
    clearTimeout(timer);
  }
}
