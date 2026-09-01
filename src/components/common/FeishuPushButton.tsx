import { useState } from 'react';
import { Send, Loader2 } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/contexts/AuthContext';
import { scoreOpportunity } from '@/lib/opportunity_scorer';
import type { Project } from '@/data/projects';

/**
 * Map client Project (camelCase) to the snake_case shape the worker's
 * buildRuleCard expects (mirrors crawler/notifier.py project dict fields).
 */
function toWorkerProject(project: Project) {
  const score = scoreOpportunity(project);
  return {
    name: project.name,
    country: project.country,
    phase: project.phase,
    summary: project.summary,
    procurement_chain: project.procurementChain,
    stainless_steel: project.stainlessSteel,
    application: project.application,
    recommendation_json: project.recommendationJson,
    opportunity_score: {
      totalScore: score.totalScore,
      grade: score.grade,
      recommendedAction: score.recommendedAction,
    },
    source_url: project.source?.url,
    source_name: project.source?.name,
    water_depth_m: project.waterDepthM,
    oil_capacity_bpd: project.oilCapacityBpd,
    gas_capacity_mmcmd: project.gasCapacityMmcmd,
    hull_type: project.hullType,
    field_name: project.fieldName,
    operator_name: project.operatorName,
    basin: project.basin,
  };
}

/**
 * 推送到飞书 — manually push the current project's card to the logged-in
 * user's Feishu via POST /api/feishu/send-card (Cloudflare Worker).
 * Unauthenticated clicks trigger Feishu OAuth login.
 *
 * variant="full" — 完整按钮（商机看板详情弹窗）
 * variant="icon" — 小号图标按钮（战报中心卡片右上角），飞书蓝描边
 */
export default function FeishuPushButton({
  project,
  variant = "full",
}: {
  project: Project;
  variant?: "full" | "icon";
}) {
  const { user, login } = useAuth();
  const [pushing, setPushing] = useState(false);

  const handlePush = async () => {
    if (pushing) return;
    if (!user) {
      toast.error('请先登录飞书');
      login();
      return;
    }
    setPushing(true);
    try {
      const resp = await fetch('/api/feishu/send-card', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ open_id: user.open_id, project: toWorkerProject(project) }),
      });
      const data = await resp.json().catch(() => ({}));
      if (!resp.ok) {
        toast.error(data.error || `推送失败 (HTTP ${resp.status})`);
        return;
      }
      toast.success('已推送到飞书');
    } catch (err) {
      toast.error(`推送失败: ${err instanceof Error ? err.message : String(err)}`);
    } finally {
      setPushing(false);
    }
  };

  if (variant === "icon") {
    return (
      <Button
        type="button"
        size="icon"
        variant="outline"
        onClick={handlePush}
        disabled={pushing}
        aria-label="推送到飞书"
        title="推送到飞书"
        className="h-7 w-7 rounded-lg border-[#3370FF]/50 text-[#3370FF] hover:bg-[#3370FF]/10"
      >
        {pushing ? (
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
        ) : (
          <Send className="h-3.5 w-3.5" />
        )}
      </Button>
    );
  }

  return (
    <Button
      size="sm"
      variant="outline"
      onClick={handlePush}
      disabled={pushing}
      className="border-[#3370FF]/40 text-[#3370FF] hover:bg-[#3370FF]/10 text-xs"
    >
      {pushing ? (
        <Loader2 className="h-3.5 w-3.5 animate-spin" />
      ) : (
        <Send className="h-3.5 w-3.5" />
      )}
      {pushing ? '推送中…' : '推送到飞书'}
    </Button>
  );
}
