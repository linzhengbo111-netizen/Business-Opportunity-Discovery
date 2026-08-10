import { useState, useCallback } from 'react';
import { supabase } from '@/db/supabase';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

/* ------------------------------------------------------------------ */
/*  types                                                              */
/* ------------------------------------------------------------------ */

export type FollowUpStatus = 'contacted' | 'valid' | 'inquiry' | 'invalid' | 'closed';

export interface FollowUp {
  id?: number;
  project_id: string;
  user_open_id: string;
  status: FollowUpStatus;
  notes: string;
  corrections: FollowUpCorrections;
  created_at?: string;
  updated_at?: string;
}

/** Sales corrections to system inferences. */
export interface FollowUpCorrections {
  /** Actual material grade if different from system recommendation. */
  actualMaterial?: string;
  /** Actual procurement timeline if different from system estimate. */
  actualProcurementDate?: string;
  /** Free-form supplementary notes about the correction. */
  additionalNotes?: string;
}

export const FOLLOW_UP_STATUS_LABELS: Record<FollowUpStatus, string> = {
  contacted: '已联系',
  valid: '有效商机',
  inquiry: '询价阶段',
  invalid: '无效',
  closed: '已成交',
};

export const FOLLOW_UP_STATUS_COLORS: Record<FollowUpStatus, string> = {
  contacted: 'bg-fpso-blue/15 text-fpso-blue border-fpso-blue/30',
  valid: 'bg-fpso-green/15 text-fpso-green border-fpso-green/30',
  inquiry: 'bg-fpso-orange/15 text-fpso-orange border-fpso-orange/30',
  invalid: 'bg-fpso-muted/15 text-fpso-muted border-fpso-muted/30',
  closed: 'bg-fpso-green/15 text-fpso-green border-fpso-green/30',
};

/* ------------------------------------------------------------------ */
/*  hook                                                               */
/* ------------------------------------------------------------------ */

export function useFollowUp() {
  const { user, isAuthenticated } = useAuth();
  const [loading, setLoading] = useState(false);

  /** Write or update a follow-up record (upsert via project_id + user_open_id). */
  const followUp = useCallback(
    async (
      projectId: string,
      status: FollowUpStatus,
      notes?: string,
      corrections?: FollowUpCorrections,
    ): Promise<FollowUp | null> => {
      if (!user?.open_id) {
        toast.error('Please log in first');
        return null;
      }

      setLoading(true);
      try {
        const payload = {
          project_id: projectId,
          user_open_id: user.open_id,
          status,
          notes: notes ?? '',
          corrections: corrections ?? {},
        };

        // Check if existing row
        const { data: existing } = await supabase
          .from('follow_ups')
          .select('id')
          .eq('project_id', projectId)
          .eq('user_open_id', user.open_id)
          .maybeSingle();

        if (existing) {
          const { data, error } = await supabase
            .from('follow_ups')
            .update(payload)
            .eq('id', existing.id)
            .select()
            .single();

          if (error) {
            toast.error(`Update failed: ${error.message}`);
            return null;
          }
          toast.success(`Follow-up status updated: ${FOLLOW_UP_STATUS_LABELS[status]}`);
          return data as FollowUp;
        } else {
          const { data, error } = await supabase
            .from('follow_ups')
            .insert(payload)
            .select()
            .single();

          if (error) {
            toast.error(`Insert failed: ${error.message}`);
            return null;
          }
          toast.success(`Follow-up recorded: ${FOLLOW_UP_STATUS_LABELS[status]}`);
          return data as FollowUp;
        }
      } catch (err) {
        console.error('followUp error:', err);
        toast.error('Failed to save follow-up');
        return null;
      } finally {
        setLoading(false);
      }
    },
    [user?.open_id],
  );

  /** Get follow-up status for a specific project (current user). */
  const getFollowUp = useCallback(
    async (projectId: string): Promise<FollowUp | null> => {
      if (!user?.open_id) return null;

      try {
        const { data, error } = await supabase
          .from('follow_ups')
          .select('*')
          .eq('project_id', projectId)
          .eq('user_open_id', user.open_id)
          .maybeSingle();

        if (error) {
          console.error('getFollowUp error:', error);
          return null;
        }
        return data as FollowUp | null;
      } catch (err) {
        console.error('getFollowUp error:', err);
        return null;
      }
    },
    [user?.open_id],
  );

  /** Get all follow-up records for the current user. */
  const getUserFollowUps = useCallback(
    async (): Promise<FollowUp[]> => {
      if (!user?.open_id) return [];

      try {
        const { data, error } = await supabase
          .from('follow_ups')
          .select('*')
          .eq('user_open_id', user.open_id)
          .order('updated_at', { ascending: false });

        if (error) {
          console.error('getUserFollowUps error:', error);
          return [];
        }
        return (data as FollowUp[]) ?? [];
      } catch (err) {
        console.error('getUserFollowUps error:', err);
        return [];
      }
    },
    [user?.open_id],
  );

  /** Get follow-ups for a given set of project IDs for the current user.
   *  Returns a Map of project_id → FollowUp for efficient lookups. */
  const getFollowUpsForProjects = useCallback(
    async (projectIds: string[]): Promise<Map<string, FollowUp>> => {
      if (!user?.open_id || projectIds.length === 0) return new Map();

      try {
        const { data, error } = await supabase
          .from('follow_ups')
          .select('*')
          .eq('user_open_id', user.open_id)
          .in('project_id', projectIds);

        if (error) {
          console.error('getFollowUpsForProjects error:', error);
          return new Map();
        }
        const map = new Map<string, FollowUp>();
        for (const row of (data as FollowUp[]) ?? []) {
          map.set(row.project_id, row);
        }
        return map;
      } catch (err) {
        console.error('getFollowUpsForProjects error:', err);
        return new Map();
      }
    },
    [user?.open_id],
  );

  return {
    loading,
    followUp,
    getFollowUp,
    getUserFollowUps,
    getFollowUpsForProjects,
    isAuthenticated,
    userOpenId: user?.open_id ?? null,
  };
}
