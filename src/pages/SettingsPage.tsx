import { useState } from 'react';
import Header from '@/components/common/Header';
import { useAuth } from '@/contexts/AuthContext';
import { useSubscription, INDUSTRY_OPTIONS } from '@/hooks/useSubscription';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';

export default function SettingsPage() {
  const { user, isAuthenticated, login } = useAuth();
  const {
    subscription,
    loading,
    countries,
    saveSubscription,
    toggleFollowProject,
    isFollowing,
  } = useSubscription();

  const [selectedIndustries, setSelectedIndustries] = useState<string[]>([]);
  const [selectedCountries, setSelectedCountries] = useState<string[]>([]);
  const [webhookUrl, setWebhookUrl] = useState('');
  const [saving, setSaving] = useState(false);

  // Sync local state from subscription once loaded
  const [synced, setSynced] = useState(false);
  if (subscription && !synced) {
    setSelectedIndustries(subscription.subscribed_industries || []);
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
    setSaving(true);
    await saveSubscription({
      subscribed_industries: selectedIndustries,
      subscribed_countries: selectedCountries,
      webhook_url: webhookUrl,
    });
    setSaving(false);
  };

  // ---- Not logged in ----
  if (!isAuthenticated) {
    return (
      <>
        <Header />
        <main className="flex flex-col flex-grow items-center justify-center gap-6 px-6">
          <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg">
            Settings
          </h1>
          <p className="text-fpso-muted text-sm">
            Please log in with Feishu to manage subscription settings.
          </p>
          <Button
            onClick={login}
            className="bg-fpso-blue hover:bg-fpso-blue/80 text-white"
          >
            Login with Feishu
          </Button>
        </main>
      </>
    );
  }

  // ---- Logged in ----
  return (
    <>
      <Header />
      <main className="mx-auto max-w-3xl flex flex-col gap-8 px-6 py-10">
        {/* Profile card */}
        <Card className="border-white/10 bg-fpso-bg/50">
          <CardHeader>
            <CardTitle className="text-fpso-fg">Profile</CardTitle>
            <CardDescription>
              Logged in as <span className="text-fpso-blue font-medium">{user?.name}</span>
            </CardDescription>
          </CardHeader>
        </Card>

        {/* Subscription card */}
        <Card className="border-white/10 bg-fpso-bg/50">
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
                        : 'border-white/10 text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                    }`}
                    onClick={() => toggleIndustry(industry)}
                  >
                    {industry}
                  </Badge>
                ))}
              </div>
            </div>

            <Separator className="bg-white/5" />

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
                        : 'border-white/10 text-fpso-muted hover:border-fpso-blue/30 hover:text-fpso-fg'
                    }`}
                    onClick={() => toggleCountry(country)}
                  >
                    {country}
                  </Badge>
                ))}
              </div>
            </div>

            <Separator className="bg-white/5" />

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
                className="bg-white/5 border-white/10 text-fpso-fg placeholder:text-fpso-muted/50"
              />
            </div>

            {/* Save */}
            <Button
              onClick={handleSave}
              disabled={saving || loading}
              className="bg-fpso-blue hover:bg-fpso-blue/80 text-white"
            >
              {saving ? 'Saving...' : 'Save Settings'}
            </Button>
          </CardContent>
        </Card>

        {/* Followed projects */}
        <Card className="border-white/10 bg-fpso-bg/50">
          <CardHeader>
            <CardTitle className="text-fpso-fg">Followed Projects</CardTitle>
            <CardDescription>
              Projects you are following will trigger [Update] notifications
              when new events are detected. Use the follow button on project pages.
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
                    onClick={() => toggleFollowProject(name)}
                  >
                    {name} ✕
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-sm text-fpso-muted">
                No followed projects yet. Visit the Database and click the follow
                button on any project to start tracking updates.
              </p>
            )}
          </CardContent>
        </Card>
      </main>
    </>
  );
}
