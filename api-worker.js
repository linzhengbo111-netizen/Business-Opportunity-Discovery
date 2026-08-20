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
      // Parse JSON safely; return upstream raw text + HTTP status on failure so
      // the exact Feishu error (credential / permission / format) is visible.
      const parseUpstream = async (resp) => {
        const text = await resp.text();
        let json = {};
        try { json = JSON.parse(text); } catch (e) { /* non-JSON upstream */ }
        return { text: text.slice(0, 500), json };
      };

      try {
        const { code } = await request.json();
        if (!code) {
          return Response.json({ error: 'Missing code parameter' }, { status: 400 });
        }
        if (!env.LARK_APP_ID || !env.LARK_APP_SECRET) {
          console.log('[feishu] missing env: app_id=%s secret=%s', !!env.LARK_APP_ID, !!env.LARK_APP_SECRET);
          return Response.json({ error: 'LARK_APP_ID/LARK_APP_SECRET not configured in worker' }, { status: 500 });
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
        const tenant = await parseUpstream(tenantResp);
        console.log('[feishu] step1 tenant_token http=%d body=%s', tenantResp.status, tenant.text);
        if (tenantResp.status !== 200 || tenant.json.code !== 0) {
          return Response.json(
            { error: 'Feishu tenant_access_token failed', step: 1, http: tenantResp.status, upstream: tenant.json },
            { status: 502 }
          );
        }

        // Step 2: exchange authorization code for user_access_token
        const oidcResp = await fetch(
          'https://open.feishu.cn/open-apis/authen/v1/oidc/access_token',
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${tenant.json.tenant_access_token}`,
            },
            body: JSON.stringify({ grant_type: 'authorization_code', code }),
          }
        );
        const oidc = await parseUpstream(oidcResp);
        console.log('[feishu] step2 oidc http=%d body=%s', oidcResp.status, oidc.text);
        if (oidcResp.status !== 200 || oidc.json.code !== 0) {
          return Response.json(
            { error: 'Feishu OIDC token exchange failed', step: 2, http: oidcResp.status, upstream: oidc.json },
            { status: 502 }
          );
        }
        const userAccessToken = oidc.json.data?.access_token;
        if (!userAccessToken) {
          return Response.json({ error: 'No access_token in response', step: 2, upstream: oidc.json }, { status: 502 });
        }

        // Step 3: get user info
        const userResp = await fetch(
          'https://open.feishu.cn/open-apis/authen/v1/user_info',
          {
            headers: { Authorization: `Bearer ${userAccessToken}` },
          }
        );
        const userInfo = await parseUpstream(userResp);
        console.log('[feishu] step3 user_info http=%d body=%s', userResp.status, userInfo.text);
        if (userResp.status !== 200 || userInfo.json.code !== 0) {
          return Response.json(
            { error: 'Feishu user_info failed', step: 3, http: userResp.status, upstream: userInfo.json },
            { status: 502 }
          );
        }

        return Response.json({
          open_id: userInfo.json.data?.open_id || '',
          name: userInfo.json.data?.name || 'Unknown',
          avatar_url: userInfo.json.data?.avatar_url || '',
        });
      } catch (err) {
        console.log('[feishu] exception: %s', String((err && err.stack) || err));
        return Response.json(
          { error: 'Internal server error', detail: String(err) },
          { status: 500 }
        );
      }
    }

    // All other requests — serve static assets (SPA)
    return env.ASSETS.fetch(request);
  },
};
