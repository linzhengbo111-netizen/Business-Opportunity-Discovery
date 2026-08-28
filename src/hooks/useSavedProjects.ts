import { useCallback, useEffect, useMemo, useState } from 'react';
import { toast } from 'sonner';
import type { Project } from '@/data/projects';
import { normalizeProjectName } from '@/data/project_aliases';

/**
 * 收藏项目 — 纯前端 localStorage 状态。
 * key: 'saved_projects'，值为项目 key 数组。
 * key = canonical id（normalizeProjectName 命中时），否则原始项目名。
 * 收藏列表永远从当前 projects 数据解析，项目被删除后自动清理（幽灵收藏）。
 */

export const SAVED_PROJECTS_KEY = 'saved_projects';

/** 项目 → 收藏 key。canonical id 优先，兜底用项目名。 */
export function projectKey(name: string): string {
  return normalizeProjectName(name) ?? name;
}

/** 从 localStorage 读取收藏 key 数组（损坏数据回退空数组）。 */
function loadSavedKeys(): string[] {
  try {
    const raw = localStorage.getItem(SAVED_PROJECTS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed)
      ? parsed.filter((x): x is string => typeof x === 'string')
      : [];
  } catch {
    return [];
  }
}

function persistKeys(keys: string[]): void {
  try {
    localStorage.setItem(SAVED_PROJECTS_KEY, JSON.stringify(keys));
  } catch {
    // localStorage 不可用（隐私模式等）— 静默降级，仅保留内存态
  }
}

export function useSavedProjects(projects: Project[]) {
  const [savedKeys, setSavedKeys] = useState<string[]>(loadSavedKeys);

  // 跨标签页同步 — 其他标签页改动收藏时刷新本页状态
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key === SAVED_PROJECTS_KEY) setSavedKeys(loadSavedKeys());
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, []);

  // 幽灵收藏清理 — projects 数据中已不存在的 key 自动移除。
  // projects 为空（数据未加载）时跳过，避免误清空。
  useEffect(() => {
    if (projects.length === 0) return;
    const liveKeys = new Set(projects.map((p) => projectKey(p.name)));
    const valid = savedKeys.filter((k) => liveKeys.has(k));
    if (valid.length !== savedKeys.length) {
      persistKeys(valid);
      setSavedKeys(valid);
    }
  }, [projects, savedKeys]);

  const isSaved = useCallback(
    (project: Project): boolean => savedKeys.includes(projectKey(project.name)),
    [savedKeys],
  );

  const toggleSaved = useCallback(
    (project: Project) => {
      const key = projectKey(project.name);
      const wasSaved = savedKeys.includes(key);
      setSavedKeys((prev) => {
        const next = wasSaved
          ? prev.filter((k) => k !== key)
          : [...prev, key];
        persistKeys(next);
        return next;
      });
      if (wasSaved) {
        toast.info('已取消收藏', { description: project.name });
      } else {
        toast.success('已收藏', { description: project.name });
      }
    },
    [savedKeys],
  );

  /** 收藏的 Project 对象列表 — 按收藏时间顺序（旧在前）。 */
  const savedProjects = useMemo(() => {
    const byKey = new Map<string, Project>();
    for (const p of projects) byKey.set(projectKey(p.name), p);
    return savedKeys
      .map((k) => byKey.get(k))
      .filter((p): p is Project => Boolean(p));
  }, [projects, savedKeys]);

  return { savedProjects, isSaved, toggleSaved };
}
