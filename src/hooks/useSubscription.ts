import { useState, useEffect, useCallback } from 'react';
import { supabase } from '@/db/supabase';
import { useAuth } from '@/contexts/AuthContext';
import { toast } from 'sonner';

/* ------------------------------------------------------------------ */
/*  types                                                              */
/* ------------------------------------------------------------------ */

export interface Subscription {
  id?: number;
  user_open_id: string;
  subscribed_industries: string[];
  subscribed_countries: string[];
  followed_project_ids: string[];
  webhook_url: string;
  created_at?: string;
  updated_at?: string;
}

const DEFAULT_SUBSCRIPTION: Omit<Subscription, 'user_open_id'> = {
  subscribed_industries: [],
  subscribed_countries: [],
  followed_project_ids: [],
  webhook_url: '',
};

/* ------------------------------------------------------------------ */
/*  available options                                                  */
/* ------------------------------------------------------------------ */

export const INDUSTRY_OPTIONS = [
  'FPSO',
  'Desalination',
  'LNG',
  'FLNG',
  'General Stainless',
  'Offshore Platform',
  'Subsea',
  'Pipeline',
  'Refinery',
  'Petrochemical',
];

/* ------------------------------------------------------------------ */
/*  hook                                                               */
/* ------------------------------------------------------------------ */

export function useSubscription() {
  const { user, isAuthenticated } = useAuth();
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [loading, setLoading] = useState(false);
  const [countries, setCountries] = useState<string[]>([]);

  // Fetch available countries from projects table
  useEffect(() => {
    supabase
      .from('projects')
      .select('country')
      .not('country', 'is', null)
      .not('country', 'eq', '')
      .order('country')
      .then(({ data }) => {
        if (data) {
          const unique = [...new Set(data.map((r: { country: string }) => r.country).filter(Boolean))];
          setCountries(unique);
        }
      })
      .catch(() => {
        // fallback: common countries
        setCountries(['Brazil', 'Guyana', 'UK', 'Norway', 'China', 'Angola', 'Nigeria', 'Malaysia']);
      });
  }, []);

  // Fetch user's subscription from Supabase
  const fetchSubscription = useCallback(async () => {
    if (!user?.open_id) {
      setSubscription(null);
      return;
    }

    setLoading(true);
    try {
      const { data, error } = await supabase
        .from('user_subscriptions')
        .select('*')
        .eq('user_open_id', user.open_id)
        .maybeSingle();

      if (error) {
        console.error('Failed to fetch subscription:', error);
        setSubscription(null);
      } else if (data) {
        setSubscription(data as Subscription);
      } else {
        // No subscription row yet — create default
        setSubscription({
          user_open_id: user.open_id,
          ...DEFAULT_SUBSCRIPTION,
        });
      }
    } catch (err) {
      console.error('useSubscription fetch error:', err);
    } finally {
      setLoading(false);
    }
  }, [user?.open_id]);

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

  // Save (upsert) subscription to Supabase
  const saveSubscription = useCallback(
    async (updates: Partial<Subscription>) => {
      if (!user?.open_id) {
        toast.error('Please log in first');
        return;
      }

      const merged = {
        ...subscription,
        ...updates,
        user_open_id: user.open_id,
      };

      setLoading(true);
      try {
        // Check if row exists
        const { data: existing } = await supabase
          .from('user_subscriptions')
          .select('id')
          .eq('user_open_id', user.open_id)
          .maybeSingle();

        let error;
        if (existing) {
          const { error: updateErr } = await supabase
            .from('user_subscriptions')
            .update({
              subscribed_industries: merged.subscribed_industries,
              subscribed_countries: merged.subscribed_countries,
              followed_project_ids: merged.followed_project_ids,
              webhook_url: merged.webhook_url,
            })
            .eq('user_open_id', user.open_id);
          error = updateErr;
        } else {
          const { error: insertErr } = await supabase
            .from('user_subscriptions')
            .insert({
              user_open_id: merged.user_open_id,
              subscribed_industries: merged.subscribed_industries,
              subscribed_countries: merged.subscribed_countries,
              followed_project_ids: merged.followed_project_ids,
              webhook_url: merged.webhook_url,
            });
          error = insertErr;
        }

        if (error) {
          toast.error(`Save failed: ${error.message}`);
          return;
        }

        setSubscription(merged as Subscription);
        toast.success('Subscription settings saved');
      } catch (err) {
        toast.error('Failed to save subscription');
        console.error(err);
      } finally {
        setLoading(false);
      }
    },
    [subscription, user?.open_id],
  );

  // Toggle follow/unfollow a project
  const toggleFollowProject = useCallback(
    async (projectName: string) => {
      if (!user?.open_id) {
        toast.error('Please log in first');
        return;
      }

      const current = subscription?.followed_project_ids || [];
      let updated: string[];

      if (current.includes(projectName)) {
        updated = current.filter((id) => id !== projectName);
        toast.info(`Unfollowed "${projectName}"`);
      } else {
        updated = [...current, projectName];
        toast.success(`Following "${projectName}"`);
      }

      await saveSubscription({ followed_project_ids: updated });
    },
    [subscription, saveSubscription, user?.open_id],
  );

  // Check if a project is followed
  const isFollowing = useCallback(
    (projectName: string): boolean => {
      return subscription?.followed_project_ids?.includes(projectName) || false;
    },
    [subscription],
  );

  return {
    subscription,
    loading,
    countries,
    fetchSubscription,
    saveSubscription,
    toggleFollowProject,
    isFollowing,
    isAuthenticated,
  };
}
