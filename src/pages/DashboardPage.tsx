/**
 * Business Opportunity Discovery
 * 深色数据终端风格单页面：全球 FPSO 项目不锈钢商机挖掘系统
 */

import { useEffect, useId, useMemo, useRef } from "react";
import PageMeta from "@/components/common/PageMeta";
import { projects, countryCoordinates } from "@/data/projects";

interface Stats {
  total: number;
  active: number;
  planned: number;
}

function getStats(): Stats {
  return {
    total: projects.length,
    active: projects.filter((p) => p.status === "Under Construction").length,
    planned: projects.filter((p) => p.status === "Planned").length,
  };
}

function getUniqueCountries(): string[] {
  const set = new Set<string>();
  for (const p of projects) {
    set.add(p.country.trim());
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
}

function getCountryFlag(country: string): string {
  const found = projects.find((p) => p.country.trim() === country.trim() && p.flag);
  return found?.flag ?? "";
}

function statusColorClass(status: string): string {
  switch (status) {
    case "Under Construction":
      return "text-fpso-blue";
    case "Delivered":
      return "text-fpso-green";
    case "Planned":
      return "text-fpso-orange";
    default:
      return "text-fpso-muted";
  }
}

function statusDotClass(status: string): string {
  switch (status) {
    case "Under Construction":
      return "bg-fpso-blue";
    case "Delivered":
      return "bg-fpso-green";
    case "Planned":
      return "bg-fpso-orange";
    default:
      return "bg-fpso-muted";
  }
}

export default function DashboardPage() {
  const uniqueId = useId();
  const selectRef = useRef<HTMLSelectElement | null>(null);

  const countries = useMemo(() => getUniqueCountries(), []);
  const stats = useMemo(() => getStats(), []);

  // 地图光点：按 x 坐标（经度）从东到西降序排列，animation-delay 依次递增
  const mapDots = useMemo(() => {
    const mapped = countries.filter((country) => countryCoordinates[country]);
    mapped.sort((a, b) => countryCoordinates[b].x - countryCoordinates[a].x);
    return mapped.map((country, index) => ({
      country,
      x: countryCoordinates[country].x,
      y: countryCoordinates[country].y,
      delay: `${index * 0.2}s`,
    }));
  }, [countries]);

  useEffect(() => {
    // 渲染统计数字
    const totalEl = document.getElementById("stat-total");
    const activeEl = document.getElementById("stat-active");
    const plannedEl = document.getElementById("stat-planned");
    if (totalEl) totalEl.textContent = String(stats.total);
    if (activeEl) activeEl.textContent = String(stats.active);
    if (plannedEl) plannedEl.textContent = String(stats.planned);

    // 渲染最后更新时间
    const lastUpdatedEl = document.getElementById("last-updated");
    if (lastUpdatedEl) {
      lastUpdatedEl.textContent = `Last updated: ${new Date().toISOString().slice(0, 10)}`;
    }

    // 动态生成国家下拉选项
    const select = document.getElementById("country-select") as HTMLSelectElement | null;
    if (select) {
      select.innerHTML = "";
      const allOption = document.createElement("option");
      allOption.value = "All Countries";
      allOption.textContent = "All Countries";
      select.appendChild(allOption);

      for (const country of countries) {
        const option = document.createElement("option");
        option.value = country.trim();
        const flag = getCountryFlag(country);
        option.textContent = flag ? `${flag} ${country}` : country;
        select.appendChild(option);
      }

      select.addEventListener("change", handleRegionChange);
      selectRef.current = select;
    }

    // 绑定地图光点点击事件（事件委托，确保延迟期间也可点击）
    const mapContainer = document.getElementById("map-container");
    const handleDotClick = (e: MouseEvent) => {
      const target = e.target as HTMLElement | null;
      if (!target) return;
      const dot = target.closest("[data-country]") as HTMLElement | null;
      if (!dot) return;
      const country = dot.dataset.country;
      if (!country) return;
      const selectEl = document.getElementById("country-select") as HTMLSelectElement | null;
      if (selectEl) {
        selectEl.value = country.trim();
        selectEl.dispatchEvent(new Event("change", { bubbles: true }));
      }
      const count = projects.filter((p) => p.country.trim() === country.trim()).length;
      if (count > 1) {
        console.log(`Clicked on ${country} (${count} projects), ready to filter list`);
      } else {
        console.log(`Clicked on ${country}, ready to filter list`);
      }
    };

    mapContainer?.addEventListener("click", handleDotClick);

    return () => {
      select?.removeEventListener("change", handleRegionChange);
      mapContainer?.removeEventListener("click", handleDotClick);
    };
  }, [countries, stats]);

  const handleRegionChange = (e: Event) => {
    const target = e.target as HTMLSelectElement | null;
    if (!target) return;
    const country = target.value.trim();
    if (country === "All Countries") {
      console.log("Region changed to: All Countries");
    } else {
      const count = projects.filter((p) => p.country.trim() === country).length;
      console.log(`Region changed to: ${country} (${count} projects)`);
    }
  };

  return (
    <>
      <PageMeta title="Business Opportunity Discovery" description="全球 FPSO 项目不锈钢商机挖掘系统" />

      {/* 顶部导航栏 */}
      <header className="sticky top-0 z-50 w-full border-b border-fpso-border bg-fpso-bg/90 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-6">
          {/* 左侧标题 */}
          <div className="flex items-center gap-2">
            <span className="text-lg font-bold tracking-tight neon-glow md:text-xl">
              Business Opportunity Discovery
            </span>
            <span className="hidden text-xs text-fpso-muted md:inline">
              Stainless Steel Opportunity Tracking in Global FPSO Projects
            </span>
          </div>

          {/* 中间导航链接（纯视觉占位） */}
          <nav className="hidden items-center gap-8 md:flex">
            <a
              href="javascript:void(0)"
              className="cursor-default text-sm font-medium text-fpso-blue"
              style={{ cursor: "default" }}
            >
              Dashboard
            </a>
            <a
              href="javascript:void(0)"
              className="cursor-default text-sm font-medium text-fpso-muted hover:text-fpso-fg"
              style={{ cursor: "default" }}
            >
              Database
            </a>
            <a
              href="javascript:void(0)"
              className="cursor-default text-sm font-medium text-fpso-muted hover:text-fpso-fg"
              style={{ cursor: "default" }}
            >
              Settings
            </a>
          </nav>

          {/* 右侧区域 */}
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <label htmlFor={`${uniqueId}-country-select`} className="hidden text-sm text-fpso-muted lg:inline">
                Region
              </label>
              <select
                id="country-select"
                className="h-9 min-w-[180px] rounded-md bg-fpso-card/85 px-3 py-1.5 text-sm text-fpso-fg outline-none ring-offset-0 focus:ring-2 focus:ring-fpso-blue/50"
              />
            </div>

            <div className="flex items-center gap-2">
              <span className="relative inline-flex h-2.5 w-2.5">
                <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-fpso-green opacity-75" />
                <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-fpso-green live-breath" />
              </span>
              <span className="text-xs font-medium tracking-wider text-fpso-green">LIVE</span>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-7xl px-6 py-10">
        {/* 页面标题 */}
        <section className="mb-10">
          <h1 className="text-2xl font-semibold tracking-tight text-fpso-fg md:text-3xl">
            全球 FPSO 项目商机挖掘
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-fpso-muted">
            聚焦 FPSO 项目中涉及不锈钢材料的需求与商机，帮助不锈钢供应链快速发现全球建造、改装、维修项目中的潜在机会。
          </p>
        </section>

        {/* 全球分布地图 */}
        <section className="mb-10">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-medium text-fpso-fg">全球分布</h2>
            <span className="text-xs text-fpso-muted">Equirectangular Projection</span>
          </div>

          <div
            id="map-container"
            className="map-container relative w-full overflow-hidden rounded-lg border border-fpso-border bg-fpso-card"
          >
            <img
              src="/world.svg"
              alt="世界地图轮廓"
              className="pointer-events-none absolute inset-0 h-auto w-full select-none"
            />
            {mapDots.map((dot) => (
              <button
                key={dot.country}
                type="button"
                data-country={dot.country}
                className="map-pulse absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 cursor-pointer rounded-full border border-fpso-blue bg-fpso-blue shadow-[0_0_10px_rgba(0,212,255,0.6)] outline-none hover:scale-110 focus:ring-2 focus:ring-fpso-blue/50"
                style={{
                  left: `${dot.x}%`,
                  top: `${dot.y}%`,
                  animationDelay: dot.delay,
                }}
                aria-label={`${dot.country} 项目`}
              />
            ))}
          </div>

          {/* 统计数据 */}
          <div className="mt-6 grid grid-cols-3 gap-4">
            <div className="rounded-lg border border-fpso-border bg-fpso-card p-4">
              <div className="text-xs font-medium uppercase tracking-wider text-fpso-muted">Total</div>
              <div
                id="stat-total"
                className="mt-2 min-w-[100px] flex-shrink-0 text-right font-mono text-3xl font-semibold text-fpso-fg"
              >
                0
              </div>
            </div>
            <div className="rounded-lg border border-fpso-border bg-fpso-card p-4">
              <div className="text-xs font-medium uppercase tracking-wider text-fpso-muted">Active</div>
              <div
                id="stat-active"
                className="mt-2 min-w-[100px] flex-shrink-0 text-right font-mono text-3xl font-semibold text-fpso-blue"
              >
                0
              </div>
            </div>
            <div className="rounded-lg border border-fpso-border bg-fpso-card p-4">
              <div className="text-xs font-medium uppercase tracking-wider text-fpso-muted">Planned</div>
              <div
                id="stat-planned"
                className="mt-2 min-w-[100px] flex-shrink-0 text-right font-mono text-3xl font-semibold text-fpso-orange"
              >
                0
              </div>
            </div>
          </div>
        </section>

        {/* 项目列表 */}
        <section>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-medium text-fpso-fg">项目列表</h2>
            <span className="text-xs text-fpso-muted">{projects.length} records</span>
          </div>

          <div id="projects-container" className="rounded-lg border border-fpso-border bg-fpso-card">
            {projects.map((project) => (
              <div
                key={project.name}
                className="project-row border-b border-fpso-border px-5 py-4 last:border-b-0"
              >
                <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
                  {/* 左侧：名称 + 标签 + 摘要 */}
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-sm font-semibold text-fpso-fg">{project.name}</h3>
                      <span className="inline-flex items-center gap-1 rounded bg-fpso-bg px-2 py-0.5 text-xs text-fpso-muted">
                        {project.flag && <span>{project.flag}</span>}
                        <span>{project.country}</span>
                      </span>
                    </div>

                    {/* 不锈钢信息预留标签 */}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <span
                        className={`tag-ss-grade tag-hidden rounded bg-fpso-blue/10 px-1.5 py-0.5 text-xs font-medium text-fpso-blue ${project.stainlessSteel ? "" : "tag-hidden"}`}
                      >
                        {project.stainlessSteel}
                      </span>
                      <span
                        className={`tag-ss-app tag-hidden rounded bg-fpso-orange/10 px-1.5 py-0.5 text-xs font-medium text-fpso-orange ${project.application ? "" : "tag-hidden"}`}
                      >
                        {project.application}
                      </span>
                    </div>

                    <div className="mt-2 flex min-w-0 items-center gap-2">
                      <span className={`status-dot h-2 w-2 flex-shrink-0 rounded-full ${statusDotClass(project.status)}`} />
                      <span className={`text-xs ${statusColorClass(project.status)}`}>{project.status}</span>
                    </div>

                    <p className="mt-2 truncate text-xs text-fpso-muted">{project.summary}</p>
                  </div>

                  {/* 右侧：来源 + 日期 */}
                  <div className="flex flex-col items-start gap-1 md:items-end md:pl-4">
                    <a
                      href={project.source.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="external-link inline-flex items-center gap-1 text-xs text-fpso-blue hover:text-fpso-blue/80"
                    >
                      <span className="link-text">{project.source.name}</span>
                      <span className="link-icon text-[0.8em] leading-none">↗</span>
                    </a>
                    <span className="text-[10px] text-fpso-dim">{project.source.date}</span>
                  </div>
                </div>
              </div>
            ))}

            {/* 空状态提示 */}
            <div className="empty-state px-5 py-10 text-center text-sm text-fpso-muted">
              No projects found for this region.
            </div>
          </div>
        </section>
      </main>

      {/* 页脚 */}
      <footer className="mt-auto border-t border-fpso-border bg-fpso-bg">
        <div className="mx-auto flex max-w-7xl flex-col items-center justify-between gap-2 px-6 py-5 md:flex-row">
          <span className="text-xs text-fpso-dim">
            Data aggregated from public sources. For internal analysis only.
          </span>
          <span id="last-updated" className="text-xs text-fpso-dim">
            Last updated: —
          </span>
        </div>
      </footer>
    </>
  );
}
