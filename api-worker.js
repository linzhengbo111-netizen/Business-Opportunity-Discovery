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

    // POST /api/feishu/send-card — manually push one project card to the
    // current user's Feishu (rule-engine card, mirrors crawler/notifier.py
    // _build_card_message with analysis=None).
    if (url.pathname === '/api/feishu/send-card' && request.method === 'POST') {
      try {
        const body = await request.json();
        const openId = String(body.open_id || '').trim();
        const project = body.project;
        if (!openId) {
          return Response.json({ error: 'Missing open_id — login required' }, { status: 401 });
        }
        if (!project || typeof project !== 'object' || !project.name) {
          return Response.json({ error: 'Missing project data' }, { status: 400 });
        }
        if (!env.LARK_APP_ID || !env.LARK_APP_SECRET) {
          return Response.json({ error: 'LARK_APP_ID/LARK_APP_SECRET not configured in worker' }, { status: 500 });
        }

        // Step 1: tenant_access_token
        const tenantResp = await fetch(
          'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ app_id: env.LARK_APP_ID, app_secret: env.LARK_APP_SECRET }),
          }
        );
        const tenantText = await tenantResp.text();
        let tenant = {};
        try { tenant = JSON.parse(tenantText); } catch (e) { /* non-JSON */ }
        console.log('[send-card] tenant_token http=%d code=%s', tenantResp.status, tenant.code);
        if (tenantResp.status !== 200 || tenant.code !== 0) {
          return Response.json({ error: 'Feishu tenant_access_token failed', upstream: tenant }, { status: 502 });
        }

        const card = buildRuleCard(project, new URL(request.url).origin);
        const sendResp = await fetch(
          'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id',
          {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              Authorization: `Bearer ${tenant.tenant_access_token}`,
            },
            body: JSON.stringify({
              receive_id: openId,
              msg_type: 'interactive',
              content: JSON.stringify(card),
            }),
          }
        );
        const sendText = await sendResp.text();
        let sendJson = {};
        try { sendJson = JSON.parse(sendText); } catch (e) { /* non-JSON */ }
        console.log('[send-card] im/messages http=%d code=%s msg=%s', sendResp.status, sendJson.code, sendJson.msg);
        if (sendResp.status !== 200 || sendJson.code !== 0) {
          return Response.json(
            { error: sendJson.msg || 'Feishu message send failed', upstream: sendJson },
            { status: 502 }
          );
        }
        return Response.json({ ok: true, message_id: sendJson.data?.message_id || '' });
      } catch (err) {
        console.log('[send-card] exception: %s', String((err && err.stack) || err));
        return Response.json({ error: 'Internal server error', detail: String(err) }, { status: 500 });
      }
    }

    // All other requests — serve static assets (SPA)
    return env.ASSETS.fetch(request);
  },
};

// Phase → procurement window estimate. Mirrors crawler/notifier.py
// _PHASE_WINDOW and src/lib/material_matcher.ts estimateProcurementWindow.
const PHASE_WINDOW = {
  procurement: '0-3 个月',
  'epc award': '2-4 个月',
  construction: '3-6 个月',
  approval: '6-12 个月',
  design: '12-18 个月',
  planning: '12 个月以上',
  concept: '12 个月以上',
  commissioning: '时间未定',
  delivery: '时间未定',
};

const LEGACY_PHASE = {
  delivered: 'Delivery',
  completed: 'Delivery',
  'under construction': 'Construction',
  planned: 'Planning',
};

function normalizePhase(phase) {
  const raw = (phase || '').trim();
  if (!raw) return '';
  return LEGACY_PHASE[raw.toLowerCase()] || raw;
}

function procurementWindow(phase) {
  const norm = normalizePhase(phase).toLowerCase();
  if (!norm) return '待补充';
  return PHASE_WINDOW[norm] || '待补充';
}

function parseRec(project) {
  const rec = project.recommendation_json;
  if (typeof rec === 'string') {
    try { return JSON.parse(rec); } catch (e) { return {}; }
  }
  return (rec && typeof rec === 'object') ? rec : {};
}

function recommendedGrades(project, rec) {
  const grades = [];
  for (const g of rec.grades || []) {
    const name = String((g && typeof g === 'object') ? (g.grade || g.name || '') : g).trim();
    if (name && !grades.includes(name)) grades.push(name);
  }
  if (!grades.length) {
    for (const g of String(project.stainless_steel || '').split(',')) {
      const name = g.trim();
      if (name && !grades.includes(name)) grades.push(name);
    }
  }
  return grades;
}

function recommendedApps(project, rec) {
  const apps = [];
  for (const a of rec.applications || []) {
    const name = String(a).trim();
    if (name && !apps.includes(name)) apps.push(name);
  }
  if (!apps.length) {
    for (const a of String(project.application || '').split(',')) {
      const name = a.trim();
      if (name && !apps.includes(name)) apps.push(name);
    }
  }
  return apps;
}

function parseScore(project) {
  let score = project.opportunity_score;
  if (typeof score === 'string') {
    try { score = JSON.parse(score); } catch (e) { score = null; }
  }
  return (score && typeof score === 'object') ? score : null;
}

/**
 * Build a Feishu card message for a project. Rule-engine display only —
 * mirrors crawler/notifier.py _build_card_message(project, analysis=None).
 */
function buildRuleCard(project, appUrl) {
  const name = String(project.name || '未命名项目').slice(0, 60);
  const summary = String(project.summary || '').trim();
  const country = String(project.country || '').trim() || '待补充';
  const phase = String(project.phase || project.status || '').trim() || '待补充';
  const chain = String(project.procurement_chain || '').trim() || '待补充';
  const sourceUrl = String(project.source_url || '').trim();
  const sourceName = String(project.source_name || '').trim();

  const windowText = procurementWindow(phase);
  const rec = parseRec(project);
  const grades = recommendedGrades(project, rec);
  const apps = recommendedApps(project, rec);

  const scoreInfo = parseScore(project);
  const scoreText =
    scoreInfo && scoreInfo.totalScore != null && scoreInfo.grade
      ? `${scoreInfo.totalScore} 分 · ${scoreInfo.grade} 级`
      : '待补充';
  const action = (scoreInfo || {}).recommendedAction || '';

  const elements = [];

  // Project identity: field/operator/basin + technical specs.
  const locItems = [];
  if (project.field_name) locItems.push(['油田/气田', String(project.field_name)]);
  if (project.operator_name) locItems.push(['运营商', String(project.operator_name)]);
  if (project.basin) locItems.push(['盆地', String(project.basin)]);
  if (project.water_depth_m) locItems.push(['水深', `${project.water_depth_m.toLocaleString('en-US')} m`]);
  if (project.oil_capacity_bpd) locItems.push(['石油产能', `${project.oil_capacity_bpd.toLocaleString('en-US')} bpd`]);
  if (project.gas_capacity_mmcmd) locItems.push(['天然气产能', `${project.gas_capacity_mmcmd.toLocaleString('en-US')} MMcmd`]);
  if (project.hull_type) locItems.push(['船体类型', String(project.hull_type)]);

  if (locItems.length) {
    elements.push({
      tag: 'div',
      text: { tag: 'lark_md', content: '📍 **项目定位**' },
    });
    const fields = locItems.map(([label, value], i) => ({
      is_short: !(i === locItems.length - 1 && locItems.length % 2 === 1),
      text: { tag: 'lark_md', content: `**${label}：** ${value}` },
    }));
    elements.push({ tag: 'div', fields });
  }

  if (summary) {
    elements.push({
      tag: 'div',
      text: { tag: 'lark_md', content: summary.length > 240 ? summary.slice(0, 240) + '...' : summary },
    });
  }

  elements.push({
    tag: 'div',
    fields: [
      { is_short: true, text: { tag: 'lark_md', content: `**国家：** ${country}` } },
      { is_short: true, text: { tag: 'lark_md', content: `**阶段：** ${phase}` } },
      { is_short: true, text: { tag: 'lark_md', content: `**机会评分：** ${scoreText}` } },
      { is_short: true, text: { tag: 'lark_md', content: `**采购时间窗（预估）：** ${windowText}` } },
    ],
  });

  if (apps.length) {
    elements.push({
      tag: 'div',
      text: { tag: 'lark_md', content: `**推荐产品：** ${apps.slice(0, 12).join('、')}` },
    });
  }

  if (grades.length) {
    elements.push({
      tag: 'div',
      text: { tag: 'lark_md', content: `**推荐不锈钢牌号：** ${grades.slice(0, 12).join('、')}` },
    });
  }

  if (action) {
    elements.push({
      tag: 'div',
      text: { tag: 'lark_md', content: `**下一步行动：** ${action}` },
    });
  }

  elements.push({
    tag: 'action',
    actions: [
      {
        tag: 'button',
        text: { tag: 'plain_text', content: 'View Details' },
        type: 'primary',
        url: `${appUrl}/database?project=${encodeURIComponent(name)}`,
      },
    ],
  });

  // Contact path block at the bottom.
  const contactLines = [];
  const hasChain = Boolean(chain && chain !== '待补充');
  if (hasChain) contactLines.push(`**EPC/承包商：** ${chain}`);
  if (sourceName) contactLines.push(`**来源：** ${sourceName}`);
  if (sourceUrl) contactLines.push(`[查看原文链接](${sourceUrl})`);
  if (hasChain) {
    const companies = chain.split(',').map((c) => c.trim()).filter(Boolean).join('、');
    contactLines.push(`建议通过 ${companies} 官网的供应商/采购入口建立联系`);
  }

  if (contactLines.length) {
    elements.push({ tag: 'hr' });
    elements.push({
      tag: 'div',
      text: { tag: 'lark_md', content: '📞 **联系路径**\n' + contactLines.join('\n') },
    });
  }

  return {
    header: {
      title: { tag: 'plain_text', content: name },
      template: 'blue',
    },
    elements,
  };
}
