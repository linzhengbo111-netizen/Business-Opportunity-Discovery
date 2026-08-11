/**
 * Cloudflare Worker — API proxy for Feishu OIDC token exchange.
 *
 * The Feishu OIDC access_token endpoint requires tenant_access_token
 * authentication, which needs app_secret. This worker keeps the secret
 * server-side and proxies the token exchange for the SPA frontend.
 */

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);

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
