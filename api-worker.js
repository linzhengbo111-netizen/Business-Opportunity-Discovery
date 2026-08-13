/**
 * Cloudflare Worker — API proxy for Feishu OIDC token exchange and LLM calls.
 *
 * The Feishu OIDC access_token endpoint requires tenant_access_token
 * authentication, which needs app_secret. The LLM endpoint (DeepSeek /
 * OpenAI-compatible) does not send CORS headers to browsers, so browser
 * calls are blocked — the worker keeps both secrets server-side and proxies
 * the requests for the SPA frontend.
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

    // GET /api/llm/status — whether the LLM API key is configured worker-side
    if (url.pathname === '/api/llm/status' && request.method === 'GET') {
      return Response.json({ configured: Boolean(env.LLM_API_KEY) });
    }

    // POST /api/llm — proxy an OpenAI Chat Completions request.
    // Body: { messages, temperature?, max_tokens?, model?, response_format? }
    if (url.pathname === '/api/llm' && request.method === 'POST') {
      try {
        const apiKey = env.LLM_API_KEY;
        if (!apiKey) {
          return Response.json({ error: 'LLM not configured' }, { status: 503 });
        }

        const body = await request.json();
        if (!Array.isArray(body.messages) || body.messages.length === 0) {
          return Response.json({ error: 'Missing messages array' }, { status: 400 });
        }

        const upstreamUrl =
          env.LLM_API_URL || 'https://api.deepseek.com/v1/chat/completions';

        const upstream = await fetch(upstreamUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            Authorization: `Bearer ${apiKey}`,
          },
          body: JSON.stringify({
            model: body.model || env.LLM_MODEL || 'deepseek-chat',
            messages: body.messages,
            temperature: body.temperature ?? 0.2,
            ...(body.max_tokens != null ? { max_tokens: body.max_tokens } : {}),
            ...(body.response_format
              ? { response_format: body.response_format }
              : {}),
          }),
        });

        const text = await upstream.text();
        if (!upstream.ok) {
          return Response.json(
            { error: 'Upstream LLM error' },
            { status: 502 }
          );
        }
        // Parse once so malformed upstream JSON becomes a clean 502
        const parsed = JSON.parse(text);
        return Response.json(parsed);
      } catch (err) {
        return Response.json({ error: 'LLM proxy error' }, { status: 502 });
      }
    }

    // POST /api/feishu/token — exchange OIDC authorization code for user info
    if (url.pathname === '/api/feishu/token' && request.method === 'POST') {
      try {
        const { code } = await request.json();
        if (!code) {
          return Response.json({ error: 'Missing code parameter' }, { status: 400 });
        }

        // Step 1: get tenant_access_token
        const tenantResp = await fetch(
          'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              app_id: env.LARK_APP_ID,
              app_secret: env.LARK_APP_SECRET,
            }),
          }
        );
        const tenantData = await tenantResp.json();
        if (tenantData.code !== 0) {
          return Response.json({ error: tenantData.msg }, { status: 400 });
        }

        // Step 2: exchange authorization code for user_access_token
        const oidcResp = await fetch(
          'https://open.feishu.cn/open-apis/authen/v1/oidc/access_token',
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${tenantData.tenant_access_token}`,
            },
            body: JSON.stringify({ grant_type: 'authorization_code', code }),
          }
        );
        const oidcData = await oidcResp.json();
        if (oidcData.code !== 0) {
          return Response.json({ error: oidcData.msg }, { status: 400 });
        }
        const userAccessToken = oidcData.data?.access_token;
        if (!userAccessToken) {
          return Response.json({ error: 'No access_token in response' }, { status: 400 });
        }

        // Step 3: get user info
        const userResp = await fetch(
          'https://open.feishu.cn/open-apis/authen/v1/user_info',
          {
            headers: { Authorization: `Bearer ${userAccessToken}` },
          }
        );
        const userData = await userResp.json();
        if (userData.code !== 0) {
          return Response.json({ error: userData.msg }, { status: 400 });
        }

        return Response.json({
          open_id: userData.data?.open_id || '',
          name: userData.data?.name || 'Unknown',
          avatar_url: userData.data?.avatar_url || '',
        });
      } catch (err) {
        return Response.json({ error: 'Internal server error' }, { status: 500 });
      }
    }

    // All other requests — serve static assets (SPA)
    return env.ASSETS.fetch(request);
  },
};
