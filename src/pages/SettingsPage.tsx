import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Header from '@/components/common/Header';
import { useAuth } from '@/contexts/AuthContext';
import { useSubscription, INDUSTRY_OPTIONS } from '@/hooks/useSubscription';
import { removeSavedByName } from '@/hooks/useSavedProjects';
import { useRequireLogin } from '@/hooks/useRequireLogin';
import { useFollowUp, FOLLOW_UP_STATUS_LABELS, FOLLOW_UP_STATUS_COLORS, type FollowUp, type FollowUpStatus } from '@/hooks/useFollowUp';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { isLLMConfigured } from '@/lib/llm_client';

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

  const toggleIndustry = (industry: string) => {
    setSelectedIndustries((prev) =>
      prev.includes(industry)
        ? prev.filter((i) => i !== industry)
        : [...prev, industry],
    );
  };

  const toggleCountry = (country: string) => {
    setSelectedCountries((prev) =>
      prev.includes(country)
        ? prev.filter((c) => c !== country)
        : [...prev, country],
    );
  };

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
      <main className="mx-auto max-w-3xl flex flex-col gap-8 px-6 py-8">
        {/* Profile card */}
        <Card className="border-border bg-fpso-bg/50">
          <CardHeader>
            <CardTitle className="text-fpso-fg">Profile</CardTitle>
            <CardDescription>
              {isAuthenticated && user ? (
                <>Logged in as <span className="text-fpso-blue font-medium">{user.name}</span></>
              ) : (
                <>Not logged in — use the Feishu login button (top right) to save subscriptions and follow-ups.</>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent>
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
        <Card className="border-border bg-fpso-bg/50">
          <CardHeader>
            <CardTitle className="text-fpso-fg">Subscription Settings</CardTitle>
            <CardDescription>
              Select industries and countries to receive push notifications
              when new matching projects are discovered.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Industries */}
            <div className="space-y-3">
              <Label className="text-fpso-fg text-sm font-medium">Industries</Label>
              <div className="flex flex-wrap gap-2">
                {INDUSTRY_OPTIONS.map((industry) => (
                  <Badge
                    key={industry}
                    variant={selectedIndustries.includes(industry) ? 'default' : 'outline'}
                    className={`cursor-pointer transition-all ${
                      selectedIndustries.includes(industry)
                        ? 'bg-fpso-blue hover:bg-fpso-blue/80'
                        : 'border-border text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                    }`}
                    onClick={() => toggleIndustry(industry)}
                  >
                    {industry}
                  </Badge>
                ))}
              </div>
            </div>

            <Separator className="bg-border/40" />

            {/* Countries */}
            <div className="space-y-3">
              <Label className="text-fpso-fg text-sm font-medium">Countries</Label>
              <p className="text-xs text-fpso-muted">
                Select countries to watch. If both industries and countries are
                selected, only projects matching BOTH will trigger notifications.
              </p>
              <div className="flex flex-wrap gap-2">
                {countries.map((country) => (
                  <Badge
                    key={country}
                    variant={selectedCountries.includes(country) ? 'default' : 'outline'}
                    className={`cursor-pointer transition-all ${
                      selectedCountries.includes(country)
                        ? 'bg-fpso-blue hover:bg-fpso-blue/80'
                        : 'border-border text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                    }`}
                    onClick={() => toggleCountry(country)}
                  >
                    {country}
                  </Badge>
                ))}
              </div>
            </div>

            <Separator className="bg-border/40" />

            {/* Webhook URL */}
            <div className="space-y-3">
              <Label htmlFor="webhook-url" className="text-fpso-fg text-sm font-medium">
                Feishu Webhook URL (optional)
              </Label>
              <p className="text-xs text-fpso-muted">
                If provided, notifications will be sent to this webhook (e.g. a group bot).
                Leave empty to receive direct messages instead.
              </p>
              <Input
                id="webhook-url"
                placeholder="https://open.feishu.cn/open-apis/bot/v2/hook/..."
                value={webhookUrl}
                onChange={(e) => setWebhookUrl(e.target.value)}
                className="bg-border/40 border-border text-fpso-fg placeholder:text-fpso-muted/50"
              />
            </div>

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

        {/* Followed projects */}
        <Card className="border-border bg-fpso-bg/50">
          <CardHeader>
            <CardTitle className="text-fpso-fg">Followed Projects</CardTitle>
            <CardDescription>
              Projects you are following will trigger [Update] notifications
              when new events are detected. Use the 收藏 button on project pages.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {subscription?.followed_project_ids &&
            subscription.followed_project_ids.length > 0 ? (
              <div className="flex flex-wrap gap-2">
                {subscription.followed_project_ids.map((name) => (
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
              <p className="text-sm text-fpso-muted">
                No followed projects yet. Visit the Database and click the 收藏
                button on any project to start tracking updates.
              </p>
            )}
          </CardContent>
        </Card>

        {/* My Follow-ups (S7) */}
        <Card className="border-border bg-fpso-bg/50">
          <CardHeader>
            <div className="flex items-center justify-between">
              <div>
                <CardTitle className="text-fpso-fg">My Follow-ups</CardTitle>
                <CardDescription>
                  Sales follow-up records with status, notes, and corrections.
                  Click a project to view details.
                </CardDescription>
              </div>
              <Button
                size="sm"
                variant="outline"
                onClick={refreshFollowUps}
                disabled={followUpsLoading}
                className="border-border text-fpso-muted hover:text-fpso-fg text-xs h-7"
              >
                {followUpsLoading ? "Loading..." : "Refresh"}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Status filter */}
            <div className="flex flex-wrap gap-1.5">
              <Badge
                variant={followUpFilter === 'all' ? 'default' : 'outline'}
                className={`cursor-pointer transition-all text-xs ${
                  followUpFilter === 'all'
                    ? 'bg-fpso-blue hover:bg-fpso-blue/80'
                    : 'border-border text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
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
                        : 'border-border text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                    }`}
                    onClick={() => setFollowUpFilter(s)}
                  >
                    {FOLLOW_UP_STATUS_LABELS[s]} ({count})
                  </Badge>
                );
              })}
            </div>

            <Separator className="bg-border/40" />

            {/* Follow-up list */}
            {followUpsLoading ? (
              <p className="text-sm text-fpso-muted">Loading...</p>
            ) : filteredFollowUps.length === 0 ? (
              <p className="text-sm text-fpso-muted">
                {followUps.length === 0
                  ? "No follow-up records yet. Visit a project and set a follow-up status to get started."
                  : "No records match the selected filter."}
              </p>
            ) : (
              <div className="space-y-2">
                {filteredFollowUps.map((fu) => (
                  <div
                    key={fu.id ?? fu.project_id}
                    onClick={() => goToProject(fu.project_id)}
                    className="flex items-start justify-between gap-3 rounded-lg border border-border bg-fpso-bg/30 px-4 py-3 cursor-pointer hover:border-fpso-blue/20 hover:bg-fpso-blue/5 transition-all group"
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
          </CardContent>
        </Card>
      </main>
    </>
  );
}
