import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, Star, Inbox, ChevronRight } from 'lucide-react';
import Header from '@/components/common/Header';
import { SearchableMultiSelect } from '@/components/common/SearchableMultiSelect';
import { useAuth } from '@/contexts/AuthContext';
import { useSubscription, INDUSTRY_OPTIONS } from '@/hooks/useSubscription';
import { removeSavedByName } from '@/hooks/useSavedProjects';
import { useRequireLogin } from '@/hooks/useRequireLogin';
import { useFollowUp, FOLLOW_UP_STATUS_LABELS, FOLLOW_UP_STATUS_COLORS, type FollowUp, type FollowUpStatus } from '@/hooks/useFollowUp';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import { toast } from 'sonner';
import { isLLMConfigured } from '@/lib/llm_client';

/** 卡片区块标题 — 全站统一的小号大写 muted 风格 */
function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs font-semibold uppercase tracking-wider text-fpso-dim">
      {children}
    </h2>
  );
}

/** 紧凑空状态 — 图标 + 简短文案 */
function EmptyState({ icon, text }: { icon: React.ReactNode; text: string }) {
  return (
    <div className="flex flex-col items-center gap-1.5 py-5 text-center">
      <span className="text-fpso-dim">{icon}</span>
      <p className="text-xs text-fpso-muted">{text}</p>
    </div>
  );
}

export default function SettingsPage() {
  const { user, isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const requireLogin = useRequireLogin();
  const {
    subscription,
    loading,
    countries,
    saveSubscription,
    toggleFollowProject,
  } = useSubscription();

  const { getUserFollowUps } = useFollowUp();
  const [followUps, setFollowUps] = useState<FollowUp[]>([]);
  const [followUpFilter, setFollowUpFilter] = useState<FollowUpStatus | 'all'>('all');
  const [followUpsLoading, setFollowUpsLoading] = useState(false);

  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [saving, setSaving] = useState(false);

  // 关注项目 Tab 内的名称过滤
  const [followedQuery, setFollowedQuery] = useState('');

  // Fetch follow-ups
  const refreshFollowUps = useCallback(async () => {
    setFollowUpsLoading(true);
    const data = await getUserFollowUps();
    setFollowUps(data);
    setFollowUpsLoading(false);
  }, [getUserFollowUps]);

  useEffect(() => {
    if (isAuthenticated) {
      refreshFollowUps();
    }
  }, [isAuthenticated, refreshFollowUps]);

  // AI engine status — worker-side secret, checked at runtime via /api/llm/status
  const [aiConfigured, setAiConfigured] = useState(false);
  useEffect(() => {
    isLLMConfigured().then(setAiConfigured);
  }, []);

  const filteredFollowUps = followUpFilter === 'all'
    ? followUps
    : followUps.filter((fu) => fu.status === followUpFilter);

  const followedProjects = (subscription?.followed_project_ids || []).filter(
    (name) => name.toLowerCase().includes(followedQuery.trim().toLowerCase()),
  );

  const goToProject = (projectId: string) => {
    navigate(`/database?project=${encodeURIComponent(projectId)}`);
  };

  // Sync local state from subscription once loaded.
  // 过滤已下线的行业（如 General Stainless），避免幽灵选项残留。
  const [synced, setSynced] = useState(false);
  if (subscription && !synced) {
    setSelectedIndustries(
      (subscription.subscribed_industries || []).filter((i) =>
        INDUSTRY_OPTIONS.some((opt) => opt === i),
      ),
    );
    setSelectedCountries(subscription.subscribed_countries || []);
    setWebhookUrl(subscription.webhook_url || '');
    setSynced(true);
  }

  const handleSave = async () => {
    if (!requireLogin()) return;
    setSaving(true);
    await saveSubscription({
      subscribed_industries: selectedIndustries,
      subscribed_countries: selectedCountries,
      webhook_url: webhookUrl,
    });
    setSaving(false);
  };

  // ---- Logged in ----
  return (
    <>
      <Header />
      <main className="mx-auto max-w-3xl flex flex-col gap-4 px-6 py-8">
        {/* Profile card */}
        <Card className="border-fpso-border bg-fpso-card/70 backdrop-blur-sm">
          <CardContent className="p-5 space-y-3">
            <SectionTitle>Profile</SectionTitle>
            <p className="text-sm text-fpso-muted">
              {isAuthenticated && user ? (
                <>Logged in as <span className="text-fpso-blue font-medium">{user.name}</span></>
              ) : (
                <>Not logged in — use the Feishu login button (top right) to save subscriptions and follow-ups.</>
              )}
            </p>
            {/* AI engine status — checks GET /api/llm/status (worker-side secret) */}
            <div className="flex items-center gap-2.5">
              <span className="relative flex h-2.5 w-2.5 flex-shrink-0">
                {aiConfigured && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fpso-green opacity-75" />
                )}
                <span
                  className={`relative inline-flex h-2.5 w-2.5 rounded-full ${
                    aiConfigured ? "bg-fpso-green" : "bg-fpso-dim"
                  }`}
                />
              </span>
              <span className={`text-sm ${aiConfigured ? "text-fpso-green" : "text-fpso-muted"}`}>
                {aiConfigured ? "AI 引擎已连接" : "规则引擎模式（未配置 AI）"}
              </span>
            </div>
          </CardContent>
        </Card>

        {/* Subscription card */}
        <Card className="border-fpso-border bg-fpso-card/70 backdrop-blur-sm">
          <CardContent className="p-5 space-y-4">
            <SectionTitle>Subscription</SectionTitle>

            {/* Industries — 可搜索多选下拉 */}
            <div className="space-y-1.5">
              <Label className="text-fpso-fg text-xs font-medium">Industries 行业</Label>
              <SearchableMultiSelect
                value={selectedIndustries}
                onChange={setSelectedIndustries}
                options={INDUSTRY_OPTIONS.map((i) => ({ value: i, label: i }))}
                placeholder="选择行业…"
                searchPlaceholder="搜索行业…"
              />
            </div>

            {/* Countries — 可搜索多选下拉 */}
            <div className="space-y-1.5">
              <Label className="text-fpso-fg text-xs font-medium">Countries 国家</Label>
              <SearchableMultiSelect
                value={selectedCountries}
                onChange={setSelectedCountries}
                options={countries.map((c) => ({ value: c, label: c }))}
                placeholder="选择国家…"
                searchPlaceholder="搜索国家…"
              />
              <p className="text-[11px] text-fpso-muted">
                行业与国家同时选择时，仅匹配两者均命中的项目才触发通知。
              </p>
            </div>

            {/* Webhook — 收进高级选项，默认折叠 */}
            <Collapsible>
              <CollapsibleTrigger asChild>
                <button
                  type="button"
                  className="group flex w-full items-center gap-1.5 text-xs font-medium text-fpso-fg transition-colors hover:text-fpso-blue"
                >
                  <ChevronRight className="h-3.5 w-3.5 text-fpso-muted transition-transform duration-200 group-data-[state=open]:rotate-90" />
                  高级选项
                  {webhookUrl.trim() !== '' && (
                    <span
                      title="已配置 Feishu Webhook"
                      className="ml-0.5 inline-block h-1.5 w-1.5 flex-shrink-0 rounded-full bg-fpso-green"
                    />
                  )}
                </button>
              </CollapsibleTrigger>
              <CollapsibleContent className="space-y-1.5 pt-2.5">
                <Label htmlFor="webhook-url" className="text-fpso-fg text-xs font-medium">
                  Feishu Webhook URL (optional)
                </Label>
                <Input
                  id="webhook-url"
                  placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="h-8 border-fpso-border bg-fpso-bg/50 text-fpso-fg text-xs placeholder:text-fpso-muted/50"
                />
                <p className="text-[11px] text-fpso-muted">
                  提供后通知将发送到该群机器人；留空则直接发送私信。
                </p>
              </CollapsibleContent>
            </Collapsible>

            {/* Save */}
            <Button
              onClick={handleSave}
              disabled={saving || loading}
              className="bg-fpso-blue hover:bg-fpso-blue/80 text-primary-foreground"
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </Button>
          </CardContent>
        </Card>

        {/* 我的项目 — 关注项目 / 跟进记录 合并为 Tab */}
        <Card className="border-fpso-border bg-fpso-card/70 backdrop-blur-sm">
          <CardContent className="p-5">
            <div className="flex items-center justify-between">
              <SectionTitle>我的项目</SectionTitle>
              <Button
                size="sm"
                variant="outline"
                onClick={refreshFollowUps}
                disabled={followUpsLoading}
                className="border-fpso-border text-fpso-muted hover:text-fpso-fg text-xs h-7"
              >
                {followUpsLoading ? "Loading..." : "Refresh"}
              </Button>
            </div>

            <Tabs defaultValue="followed" className="mt-3">
              <TabsList className="h-8 w-full justify-start gap-1 rounded-lg border border-fpso-border bg-fpso-bg/50 p-0.5">
                <TabsTrigger
                  value="followed"
                  className="h-7 flex-1 rounded-md px-2 text-xs font-medium text-fpso-muted hover:text-fpso-fg data-[state=active]:bg-fpso-blue/10 data-[state=active]:text-fpso-blue data-[state=active]:shadow-none"
                >
                  关注项目 ({subscription?.followed_project_ids?.length ?? 0})
                </TabsTrigger>
                <TabsTrigger
                  value="followups"
                  className="h-7 flex-1 rounded-md px-2 text-xs font-medium text-fpso-muted hover:text-fpso-fg data-[state=active]:bg-fpso-blue/10 data-[state=active]:text-fpso-blue data-[state=active]:shadow-none"
                >
                  跟进记录 ({followUps.length})
                </TabsTrigger>
              </TabsList>

              {/* Tab 1 — Followed projects */}
              <TabsContent value="followed" className="mt-3 space-y-3">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-2 top-1/2 h-3 w-3 -translate-y-1/2 text-fpso-muted" />
                  <input
                    value={followedQuery}
                    onChange={(e) => setFollowedQuery(e.target.value)}
                    placeholder="搜索项目…"
                    className="h-7 w-full rounded-md border border-fpso-border bg-fpso-bg/50 pl-7 pr-2 text-xs text-fpso-fg outline-none placeholder:text-fpso-muted/50 focus:border-fpso-blue/50"
                  />
                </div>

                {followedProjects.length > 0 ? (
                  <div className="flex flex-wrap gap-1.5">
                    {followedProjects.map((name) => (
                      <Badge
                        key={name}
                        variant="outline"
                        className="border-fpso-blue/30 text-fpso-blue cursor-pointer hover:bg-fpso-blue/10"
                        onClick={() => {
                          toggleFollowProject(name);
                          removeSavedByName(name);
                          toast.info(`已取消收藏 "${name}"`);
                        }}
                      >
                        {name} ✕
                      </Badge>
                    ))}
                  </div>
                ) : (
                  <EmptyState
                    icon={<Star className="h-5 w-5" />}
                    text={
                      subscription?.followed_project_ids?.length
                        ? "没有匹配的项目"
                        : "暂无关注项目 — 在项目页点击收藏按钮即可追踪更新"
                    }
                  />
                )}
              </TabsContent>

              {/* Tab 2 — My Follow-ups (S7) */}
              <TabsContent value="followups" className="mt-3 space-y-3">
                {/* Status filter */}
                <div className="flex flex-wrap gap-1.5">
                  <Badge
                    variant={followUpFilter === 'all' ? 'default' : 'outline'}
                    className={`cursor-pointer transition-all text-xs ${
                      followUpFilter === 'all'
                        ? 'bg-fpso-blue hover:bg-fpso-blue/80'
                        : 'border-fpso-border text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                    }`}
                    onClick={() => setFollowUpFilter('all')}
                  >
                    All ({followUps.length})
                  </Badge>
                  {(['contacted', 'valid', 'inquiry', 'invalid', 'closed'] as FollowUpStatus[]).map((s) => {
                    const count = followUps.filter((fu) => fu.status === s).length;
                    return (
                      <Badge
                        key={s}
                        variant={followUpFilter === s ? 'default' : 'outline'}
                        className={`cursor-pointer transition-all text-xs ${
                          followUpFilter === s
                            ? 'bg-fpso-blue hover:bg-fpso-blue/80'
                            : 'border-fpso-border text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                        }`}
                        onClick={() => setFollowUpFilter(s)}
                      >
                        {FOLLOW_UP_STATUS_LABELS[s]} ({count})
                      </Badge>
                    );
                  })}
                </div>

                {/* Follow-up list */}
                {followUpsLoading ? (
                  <p className="text-sm text-fpso-muted">Loading...</p>
                ) : filteredFollowUps.length === 0 ? (
                  <EmptyState
                    icon={<Inbox className="h-5 w-5" />}
                    text={
                      followUps.length === 0
                        ? "暂无跟进记录 — 在项目页设置跟进状态即可开始"
                        : "没有匹配当前状态的记录"
                    }
                  />
                ) : (
                  <div className="space-y-2">
                    {filteredFollowUps.map((fu) => (
                      <div
                        key={fu.id ?? fu.project_id}
                        onClick={() => goToProject(fu.project_id)}
                        className="flex items-start justify-between gap-3 rounded-lg border border-fpso-border bg-fpso-bg/30 px-4 py-3 cursor-pointer hover:border-fpso-blue/20 hover:bg-fpso-blue/5 transition-all group"
                      >
                        <div className="min-w-0 flex-1">
                          <p className="text-sm font-medium text-fpso-fg truncate group-hover:text-fpso-blue transition-colors">
                            {fu.project_id}
                          </p>
                          {fu.notes && (
                            <p className="text-xs text-fpso-dim mt-0.5 truncate">{fu.notes}</p>
                          )}
                          {fu.updated_at && (
                            <p className="text-[10px] text-fpso-muted/60 mt-1">
                              {new Date(fu.updated_at).toLocaleString("zh-CN", {
                                year: "numeric",
                                month: "2-digit",
                                day: "2-digit",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                            </p>
                          )}
                        </div>
                        <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[10px] font-medium border flex-shrink-0 ${FOLLOW_UP_STATUS_COLORS[fu.status]}`}>
                          {FOLLOW_UP_STATUS_LABELS[fu.status]}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </main>
    </>
  );
}
