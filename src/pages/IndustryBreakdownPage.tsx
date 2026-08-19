/**
 * IndustryBreakdownPage — 海水淡化系统 3D 工艺流程交互式可视化
 * =============================================================================
 * 深色数据终端风格。核心功能：
 *   1. Canvas 渲染海水淡化全景图 + 多边形区域遮罩
 *   2. 鼠标悬浮底部缩略板块 → Canvas 材质色高亮 + 其余变暗 (交叉淡入淡出)
 *   3. 右侧面板：管道材质色卡 + 主要设备表
 *   4. 所有颜色 / 透明度 / 过渡时间集中为可配置常量
 *
 * 图片路径：将原图放入 public/images/desalination-process.jpg
 *           或拖拽任意图片到 Canvas 区域临时替换。
 *
 * 坐标数据修改：编辑 REGION_MASKS 对象中的 polys 数组。
 * 底部模块增删：编辑 THUMB_ITEMS 数组。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTheme } from "next-themes";
import Header from "@/components/common/Header";
import PageMeta from "@/components/common/PageMeta";

// ═══════════════════════════════════════════════════════════════════════════════
// 可配置常量 —— 修改此处即可调整所有视觉参数
// ═══════════════════════════════════════════════════════════════════════════════

/** 原图路径 (Vite public 目录)。设为空字符串 "" 则仅显示暗色背景+遮罩预览。 */
const IMAGE_PATH = "/images/desalination-process.jpg";

/** hover 过渡动画时长 (ms)。影响 Canvas 交叉淡入淡出和缩略图 CSS transition。 */
const TRANSITION_MS = 300;

/** 非高亮区域暗色遮罩最大不透明度 (0-1)。hover 时非目标区域变暗程度。 */
const DIM_OPACITY = 0.28;

/** 高亮区域材质色叠加最大不透明度 (0-1)。目标区域染色强度。 */
const HIGHLIGHT_OPACITY = 0.15;

/** 默认(idle)状态下所有区域材质色叠加不透明度 (0-1)。 */
const IDLE_REGION_OPACITY = 0.06;

/** 无图片时的占位背景色（暗色） */
const PLACEHOLDER_BG_DARK = "#0d1117";

/** 无图片时的占位背景色（浅色） */
const PLACEHOLDER_BG_LIGHT = "#f0f4f8";

/** 无图片时的网格线颜色（暗色） */
const PLACEHOLDER_GRID_DARK = "rgba(56,139,253,0.06)";

/** 无图片时的网格线颜色（浅色） */
const PLACEHOLDER_GRID_LIGHT = "rgba(15,23,42,0.05)";

// ── 底部缩略板块 ──

/** 底部缩略板块 hover 时 CSS scale */
const THUMB_SCALE = 1.07;

/** 底部缩略板块 hover 外发光 (CSS box-shadow 值) */
const THUMB_GLOW = "0 0 22px";

/** 底部缩略板块非选中时 CSS opacity */
const THUMB_DIM_OPACITY = 0.35;

// ═══════════════════════════════════════════════════════════════════════════════
// 管道材质色卡 — 与右上角「管道材质选用总览」一一对应
// ═══════════════════════════════════════════════════════════════════════════════

interface MaterialSpec {
  name: string;    // 材质牌号
  color: string;   // 对应配色 (hex)
  desc: string;    // 用途简述
}

const MATERIAL_COLORS: MaterialSpec[] = [
  { name: "304L",  color: "#A0A0A0", desc: "低压辅助管路" },
  { name: "316L",  color: "#6CB4D9", desc: "预处理/低压系统" },
  { name: "2205",  color: "#2B5C8F", desc: "取水/浓水排放" },
  { name: "2507",  color: "#7B4FA0", desc: "高压泵/RO管道/膜壳" },
  { name: "904L",  color: "#F4A340", desc: "CIP 清洗系统" },
  { name: "钛材",  color: "#8DD3C7", desc: "特殊耐腐蚀部位" },
];

// ═══════════════════════════════════════════════════════════════════════════════
// 区域遮罩坐标 — 由坐标拾取工具生成，原图像素坐标系
// ★ 修改区域高亮位置：直接编辑下方 polys 坐标数组 (图片像素坐标)
// ═══════════════════════════════════════════════════════════════════════════════

interface PolyPoint { x: number; y: number; }
interface RegionMask {
  color: string;    // 材质色
  label: string;    // 显示名称
  polys: PolyPoint[][]; // 多边形数组，每个多边形为一个闭合顶点序列
}

const REGION_MASKS: Record<string, RegionMask> = {
  pretreatment: {
    color: "#6CB4D9",
    label: "预处理系统(316L)",
    polys: [
      [{ x: 155, y: 692 }, { x: 307, y: 694 }, { x: 312, y: 1010 }, { x: 161, y: 1008 }],
    ],
  },
  intake: {
    color: "#2B5C8F",
    label: "取水系统(2205)",
    polys: [
      [{ x: 5, y: 695 }, { x: 141, y: 693 }, { x: 145, y: 1010 }, { x: 6, y: 1010 }, { x: 10, y: 691 }],
    ],
  },
  hpp: {
    color: "#7B4FA0",
    label: "高压泵系统(2205/2507)",
    polys: [[{ x: 322, y: 694 }, { x: 516, y: 696 }, { x: 518, y: 1017 }, { x: 329, y: 1011 }, { x: 327, y: 692 }]],
  },
  roPipe: {
    color: "#7B4FA0",
    label: "RO高压管道(2507)",
    polys: [[{ x: 529, y: 697 }, { x: 690, y: 696 }, { x: 690, y: 1010 }, { x: 535, y: 1011 }, { x: 529, y: 697 }]],
  },
  roMembrane: {
    color: "#7B4FA0",
    label: "RO膜壳(2507)",
    polys: [[{ x: 707, y: 696 }, { x: 845, y: 697 }, { x: 849, y: 1013 }, { x: 701, y: 1011 }, { x: 701, y: 684 }]],
  },
  cip: {
    color: "#F4A340",
    label: "CIP系统(904L)",
    polys: [[{ x: 858, y: 697 }, { x: 994, y: 697 }, { x: 996, y: 1010 }, { x: 860, y: 1008 }, { x: 858, y: 697 }]],
  },
  brine: {
    color: "#2B5C8F",
    label: "浓水排放管道(2205/2507)",
    polys: [[{ x: 1006, y: 697 }, { x: 1142, y: 694 }, { x: 1142, y: 1013 }, { x: 1011, y: 1017 }, { x: 1009, y: 697 }]],
  },
};

// ═══════════════════════════════════════════════════════════════════════════════
// 底部缩略板块定义 — 7 个模块（取水系统暂无坐标数据，显示占位）
// ★ 增删模块、修改材质标签或主题色在此编辑。key 需与 REGION_MASKS key 匹配。
// ═══════════════════════════════════════════════════════════════════════════════

interface ThumbItem {
  key: string;            // 对应 REGION_MASKS key，或特殊标识 (如 intake)
  label: string;          // 显示名称
  material: string;       // 材质牌号标签
  color: string;          // 缩略图主题色
  placeholder?: boolean;  // 为 true 时显示"坐标待标定"
}

const THUMB_ITEMS: ThumbItem[] = [
  { key: "intake",       label: "取水系统",        material: "2205",      color: "#2B5C8F" },
  { key: "pretreatment", label: "预处理系统",      material: "316L",      color: "#6CB4D9" },
  { key: "hpp",          label: "高压泵系统",      material: "2205/2507", color: "#7B4FA0" },
  { key: "roPipe",       label: "RO高压管道",      material: "2507",      color: "#7B4FA0" },
  { key: "roMembrane",   label: "RO膜壳",          material: "2507",      color: "#7B4FA0" },
  { key: "cip",          label: "CIP 系统",         material: "904L",      color: "#F4A340" },
  { key: "brine",        label: "浓水排放管道",    material: "2205/2507", color: "#2B5C8F" },
];

// ═══════════════════════════════════════════════════════════════════════════════
// 主要设备表
// ═══════════════════════════════════════════════════════════════════════════════

interface EquipmentRow {
  no: number;
  name: string;
  spec: string;
  material: string;
}

const EQUIPMENT_TABLE: EquipmentRow[] = [
  { no: 1,  name: "取水泵",           spec: "Q=1500m³/h",        material: "2205" },
  { no: 2,  name: "多介质过滤器",     spec: "Φ3200×4500",        material: "316L" },
  { no: 3,  name: "超滤 UF 膜组",     spec: "80 支/套",           material: "316L" },
  { no: 4,  name: "保安过滤器",       spec: "5μm, Φ600",          material: "316L" },
  { no: 5,  name: "高压泵",           spec: "Q=850m³/h, H=650m", material: "2507" },
  { no: 6,  name: "RO 膜壳",          spec: '8", 1200psi',       material: "2507" },
  { no: 7,  name: "RO 膜元件",        spec: "SW440i, 8040",      material: "—" },
  { no: 8,  name: "CIP 清洗罐",       spec: "V=20m³",            material: "904L" },
  { no: 9,  name: "浓水排放管",       spec: "DN300",              material: "2205/2507" },
  { no: 10, name: "药剂加注装置",     spec: "5 路计量泵",         material: "316L" },
];

// ═══════════════════════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════════════════════

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}

/** 构建多边形路径 (仅 path 操作，不 fill/stroke) */
function buildPolyPath(ctx: CanvasRenderingContext2D, vertices: PolyPoint[]) {
  if (vertices.length < 2) return;
  ctx.beginPath();
  ctx.moveTo(vertices[0].x, vertices[0].y);
  for (let i = 1; i < vertices.length; i++) {
    ctx.lineTo(vertices[i].x, vertices[i].y);
  }
  ctx.closePath();
}

// ═══════════════════════════════════════════════════════════════════════════════
// 主组件
// ═══════════════════════════════════════════════════════════════════════════════

export default function IndustryBreakdownPage() {
  // ---- 状态 ----
  const [image, setImage] = useState<HTMLImageElement | null>(null);
  const [imgSize, setImgSize] = useState<{ w: number; h: number }>({ w: 1200, h: 1050 });

  // hovered 驱动 CSS (缩略图过渡)，animAlpha 驱动 Canvas 交叉淡入淡出
  const [hovered, setHovered] = useState<string | null>(null);
  const [animAlpha, setAnimAlpha] = useState(0); // 0=idle, 1=hover-highlight

  // ---- refs (不触发重渲染的值) ----
  const containerRef  = useRef<HTMLDivElement>(null);
  const canvasRef     = useRef<HTMLCanvasElement>(null);
  const containerSize = useRef<{ w: number; h: number }>({ w: 800, h: 500 });

  // 动画用 refs — 避免 effect 依赖 hovered/animAlpha 导致循环重建
  const animTarget    = useRef(0);   // 目标 alpha: 0 或 1
  const animStartAlpha = useRef(0);  // 动画起始 alpha
  const animStartTime  = useRef(0);  // performance.now()
  const rafRef         = useRef(0);

  // ResizeObserver 回调中读取的最新值 (避免 RO 依赖变化)
  const hoveredRef    = useRef<string | null>(null);
  const animAlphaRef  = useRef(0);
  // 主题状态通过 ref 供 renderFrame 读取（Canvas 2D 不感知 CSS 变量）
  const { theme } = useTheme();
  const isLight = theme === 'light';
  const themeRef = useRef(isLight);
  themeRef.current = isLight;
  // 同步 refs
  hoveredRef.current   = hovered;
  animAlphaRef.current = animAlpha;

  // ---- 工具: Canvas 尺寸适配 ----
  const resizeCanvas = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const { w, h } = containerSize.current;
    if (canvas.width === w * dpr && canvas.height === h * dpr) return; // 无变化跳过
    canvas.width  = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width  = w + "px";
    canvas.style.height = h + "px";
  }, []);

  // ---- 工具: 计算 图片坐标 → Canvas 坐标 的变换 ----
  const getTransform = useCallback(() => {
    const cw = containerSize.current.w;
    const ch = containerSize.current.h;
    if (cw === 0 || ch === 0) return { scale: 1, ox: 0, oy: 0 };
    const iw = imgSize.w;
    const ih = imgSize.h;
    const scale = Math.min(cw / iw, ch / ih);
    const ox = (cw - iw * scale) / 2;
    const oy = (ch - ih * scale) / 2;
    return { scale, ox, oy };
  }, [imgSize]);

  // ---- 核心渲染 (通过 ref 读取 hovered/animAlpha，避免闭包过期) ----
  const renderFrame = useCallback((activeKey: string | null, alpha: number) => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const dpr = window.devicePixelRatio || 1;
    const cw = containerSize.current.w;
    const ch = containerSize.current.h;
    if (cw === 0 || ch === 0) return;

    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);

    const { scale, ox, oy } = getTransform();
    const iw = imgSize.w;
    const ih = imgSize.h;

    ctx.save();
    ctx.translate(ox, oy);
    ctx.scale(scale, scale);

    // ── 1. 背景层: 图片 或 暗色占位 ──
    if (image) {
      ctx.drawImage(image, 0, 0, iw, ih);
    } else {
      // 主题占位背景 + 细网格
      ctx.fillStyle = themeRef.current ? PLACEHOLDER_BG_LIGHT : PLACEHOLDER_BG_DARK;
      ctx.fillRect(0, 0, iw, ih);
      ctx.strokeStyle = themeRef.current ? PLACEHOLDER_GRID_LIGHT : PLACEHOLDER_GRID_DARK;
      ctx.lineWidth = 1;
      const grid = 40;
      for (let x = grid; x < iw; x += grid) { ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, ih); ctx.stroke(); }
      for (let y = grid; y < ih; y += grid) { ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(iw, y); ctx.stroke(); }
    }

    // ── 2. 遮罩/高亮层 (alpha 驱动交叉淡入淡出) ──
    const hasRegion = activeKey ? (REGION_MASKS[activeKey] != null) : false;

    if (alpha > 0.005) {
      if (hasRegion) {
        // 反转路径: 覆盖非高亮区域，保留高亮区原图可见
        const region = REGION_MASKS[activeKey!];
        ctx.save();
        ctx.beginPath();
        // 外框: 整张画布
        ctx.rect(0, 0, iw, ih);
        // 内孔: 逆时针画高亮区域多边形 (与外框反向 = 挖洞)
        for (const poly of region.polys) {
          if (poly.length < 3) continue;
          const last = poly[poly.length - 1];
          ctx.moveTo(last.x, last.y);
          for (let i = poly.length - 2; i >= 0; i--) {
            ctx.lineTo(poly[i].x, poly[i].y);
          }
          ctx.closePath();
        }
        ctx.fillStyle = `rgba(0,0,0,${DIM_OPACITY * alpha})`;
        ctx.fill("evenodd");
        ctx.restore();

        // 高亮区: 材质色半透明叠加在原图上
        for (const poly of region.polys) {
          buildPolyPath(ctx, poly);
          ctx.fillStyle = hexToRgba(region.color, HIGHLIGHT_OPACITY * alpha);
          ctx.fill();
          ctx.strokeStyle = hexToRgba(region.color, 0.85 * alpha);
          ctx.lineWidth = 2 / scale;
          ctx.stroke();
        }
      } else {
        // 无坐标数据的模块: 全图均匀变暗
        ctx.fillStyle = `rgba(0,0,0,${DIM_OPACITY * alpha})`;
        ctx.fillRect(0, 0, iw, ih);
      }
    }

    // (C) idle 区域叠加 (alpha 越低越明显 → 1-alpha)
    const idleAlpha = IDLE_REGION_OPACITY * (1 - alpha);
    if (idleAlpha > 0.002) {
      for (const region of Object.values(REGION_MASKS)) {
        for (const poly of region.polys) {
          buildPolyPath(ctx, poly);
          ctx.fillStyle = hexToRgba(region.color, idleAlpha);
          ctx.fill();
        }
      }
    }

    ctx.restore();

    // ── 3. 占位提示 (取水系统 hover，无坐标数据) ──
    if (activeKey && !hasRegion && alpha > 0.5) {
      const textAlpha = 0.7 * Math.min(1, (alpha - 0.5) * 2);
      ctx.fillStyle = themeRef.current
        ? `rgba(15,23,42,${textAlpha})`
        : `rgba(255,255,255,${textAlpha})`;
      ctx.font = `${14 * dpr}px -apple-system, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText("⚠ 取水系统坐标数据待标定 — 请使用坐标拾取工具标定后更新 REGION_MASKS", cw / 2, ch / 2);
    }

    // ── 4. 无图片时的中央提示 ──
    if (!image) {
      ctx.fillStyle = themeRef.current ? "rgba(15,23,42,0.35)" : "rgba(255,255,255,0.2)";
      ctx.font = `${13 * dpr}px -apple-system, sans-serif`;
      ctx.textAlign = "center";
      ctx.fillText("拖拽工艺图至此 或 将图片放入 public/images/desalination-process.png", cw / 2, ch / 2 - 72);
      ctx.fillText("当前显示区域遮罩预览 (基于标定坐标)", cw / 2, ch / 2 - 52);
    }
  }, [image, imgSize, getTransform]);

  // ═══════════════════════════════════════════════════════════════════════════
  // Effect 1: 加载原图 (仅挂载一次)
  // ═══════════════════════════════════════════════════════════════════════════
  useEffect(() => {
    let cancelled = false;
    if (!IMAGE_PATH) return; // 空字符串 = 不加载，使用暗色背景

    const img = new Image();
    img.onload = () => {
      if (cancelled) return;
      setImage(img);
      setImgSize({ w: img.naturalWidth, h: img.naturalHeight });
    };
    img.onerror = () => {
      if (cancelled) return;
      console.warn("[IndustryBreakdown] 图片加载失败: " + IMAGE_PATH + "  — 将渲染暗色背景 + 遮罩预览");
    };
    img.src = IMAGE_PATH;
    return () => { cancelled = true; };
  }, []);

  // ═══════════════════════════════════════════════════════════════════════════
  // Effect 2: ResizeObserver — 仅挂载一次，通过 ref 读取最新值
  // ═══════════════════════════════════════════════════════════════════════════
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width === 0 && height === 0) continue;
        containerSize.current = { w: width, h: height };
        resizeCanvas();
        // 直接渲染，不通过 React state (避免延迟)
        renderFrame(hoveredRef.current, animAlphaRef.current);
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [resizeCanvas, renderFrame]); // renderFrame 引用稳定 (useCallback 依赖 image/imgSize)

  // ═══════════════════════════════════════════════════════════════════════════
  // Effect 3: hover 动画 — animAlpha 平滑过渡到 0 或 1
  // ═══════════════════════════════════════════════════════════════════════════
  useEffect(() => {
    const target = hovered ? 1 : 0;
    animTarget.current = target;
    animStartAlpha.current = animAlphaRef.current;
    animStartTime.current = performance.now();

    function tick(now: number) {
      const elapsed = now - animStartTime.current;
      const raw = Math.min(1, elapsed / TRANSITION_MS);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - raw, 3);

      const from = animStartAlpha.current;
      const to   = animTarget.current;
      const current = from + (to - from) * eased;
      animAlphaRef.current = current;
      setAnimAlpha(current);

      if (raw < 1) {
        rafRef.current = requestAnimationFrame(tick);
      }
    }
    rafRef.current = requestAnimationFrame(tick);

    return () => cancelAnimationFrame(rafRef.current);
  }, [hovered]);

  // ═══════════════════════════════════════════════════════════════════════════
  // Effect 4: Canvas 渲染 — 当 animAlpha / image / imgSize 变化时重绘
  // ═══════════════════════════════════════════════════════════════════════════
  useEffect(() => {
    resizeCanvas();
    renderFrame(hovered, animAlpha);
  }, [animAlpha, image, imgSize, hovered, isLight, resizeCanvas, renderFrame]);

  // ═══════════════════════════════════════════════════════════════════════════
  // 拖拽图片处理
  // ═══════════════════════════════════════════════════════════════════════════
  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (!file || !file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        setImage(img);
        setImgSize({ w: img.naturalWidth, h: img.naturalHeight });
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  }, []);

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
  }, []);

  // ═══════════════════════════════════════════════════════════════════════════
  // hover 处理器 (仅设 target，动画由 effect 3 接管)
  // ═══════════════════════════════════════════════════════════════════════════
  function handleThumbEnter(key: string) { setHovered(key); }
  function handleThumbLeave()             { setHovered(null); }

  // hover 指示条文案
  const activeLabel = hovered
    ? (REGION_MASKS[hovered]?.label ?? THUMB_ITEMS.find((t) => t.key === hovered)?.label ?? "")
    : "";

  // ═══════════════════════════════════════════════════════════════════════════
  // JSX
  // ═══════════════════════════════════════════════════════════════════════════
  return (
    <div className="flex flex-col" style={{ height: "100vh" }}>
      <PageMeta title="行业拆解 — 海水淡化工艺可视化" description="海水淡化系统 3D 工艺流程与管道材质交互式可视化" />
      <Header rightContent={
        <div className="flex items-center gap-3 text-xs text-fpso-muted">
          <span className="inline-block w-2 h-2 rounded-full bg-fpso-green live-breath" />
          <span>INTERACTIVE</span>
        </div>
      } />

      {/* 主体: Canvas + 侧边栏 */}
      <div className="flex flex-1 overflow-hidden" style={{ minHeight: 0 }}>
        {/* Canvas 区域 */}
        <div
          ref={containerRef}
          className="flex-1 relative bg-card dark:bg-[#0a0a12] overflow-hidden transition-theme"
          onDrop={handleDrop}
          onDragOver={handleDragOver}
        >
          <canvas ref={canvasRef} className="block absolute inset-0" />

          {/* hover 状态指示条 */}
          {hovered && (
            <div
              className="absolute top-3 left-1/2 -translate-x-1/2 px-4 py-1.5 rounded-full text-xs font-medium
                         bg-black/70 backdrop-blur border border-white/15 text-white pointer-events-none z-10"
              style={{ transition: `opacity ${TRANSITION_MS}ms ease` }}
            >
              当前高亮：<span style={{ color: REGION_MASKS[hovered]?.color ?? "#888" }}>{activeLabel}</span>
              {!REGION_MASKS[hovered] && " — 坐标待标定"}
            </div>
          )}
        </div>

        {/* 右侧面板 */}
        <aside className="w-72 flex-shrink-0 border-l border-fpso-border bg-fpso-bg/60 overflow-y-auto">
          {/* 管道材质色卡 */}
          <div className="p-4 border-b border-fpso-border">
            <h3 className="text-xs font-bold uppercase tracking-wider text-fpso-muted mb-3">
              🎨 管道材质选用总览
            </h3>
            <div className="space-y-2">
              {MATERIAL_COLORS.map((m) => (
                <div key={m.name} className="flex items-center gap-2.5 text-xs">
                  <span
                    className="inline-block w-3.5 h-3.5 rounded-sm flex-shrink-0 border border-border"
                    style={{ background: m.color }}
                  />
                  <span className="font-mono text-fpso-fg w-10">{m.name}</span>
                  <span className="text-fpso-dim">{m.desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* 主要设备表 */}
          <div className="p-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-fpso-muted mb-3">
              📋 主要设备表
            </h3>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-fpso-dim border-b border-fpso-border/50">
                  <th className="text-left py-1.5 pr-2 w-6">#</th>
                  <th className="text-left py-1.5 pr-2">设备</th>
                  <th className="text-left py-1.5 pr-2">规格</th>
                  <th className="text-left py-1.5">材质</th>
                </tr>
              </thead>
              <tbody>
                {EQUIPMENT_TABLE.map((eq) => {
                  const mat = eq.material.split("/")[0].trim();
                  const spec = MATERIAL_COLORS.find((m) => m.name === mat || eq.material.includes(m.name));
                  return (
                    <tr key={eq.no} className="border-b border-fpso-border/20 hover:bg-white/[0.03]">
                      <td className="py-1.5 pr-2 text-fpso-dim">{eq.no}</td>
                      <td className="py-1.5 pr-2 text-fpso-fg">{eq.name}</td>
                      <td className="py-1.5 pr-2 text-fpso-dim font-mono">{eq.spec}</td>
                      <td className="py-1.5">
                        <span
                          className="px-1.5 py-0.5 rounded text-[10px] font-mono"
                          style={{
                            background: spec ? hexToRgba(spec.color, 0.2) : "transparent",
                            color: spec?.color ?? "#888",
                            border: `1px solid ${spec ? hexToRgba(spec.color, 0.35) : "transparent"}`,
                          }}
                        >
                          {eq.material}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* 备注 */}
          <div className="p-4 border-t border-fpso-border">
            <p className="text-[11px] text-fpso-dim leading-relaxed">
              <strong className="text-fpso-muted">备注：</strong>
              管道材质依据介质腐蚀性、压力等级、温度范围综合选型。
              高压段（RO进水/浓水）采用超级双相钢 2507；
              取水/排放段采用双相钢 2205；
              CIP 清洗系统采用 904L 耐酸碱。
            </p>
          </div>
        </aside>
      </div>

      {/* ════════════ 底部缩略板块 ════════════ */}
      <div
        className="flex-shrink-0 border-t border-fpso-border bg-card dark:bg-[#0c0c16] transition-theme"
        style={{ height: 130 }}
      >
        <div className="flex items-stretch h-full">
          {THUMB_ITEMS.map((item) => {
            const isActive = hovered === item.key;
            const isDimmed = hovered !== null && !isActive;

            return (
              <div
                key={item.key}
                className={`
                  flex-1 flex flex-col items-center justify-center gap-1.5 cursor-pointer select-none
                  border-r border-fpso-border/30 last:border-r-0
                  transition-all ease-out relative
                `}
                style={{
                  transitionDuration: `${TRANSITION_MS}ms`,
                  transform: isActive ? `scale(${THUMB_SCALE})` : "scale(1)",
                  opacity: isDimmed ? THUMB_DIM_OPACITY : 1,
                  boxShadow: isActive
                    ? `${THUMB_GLOW} ${hexToRgba(item.color, 0.55)}`
                    : "none",
                  zIndex: isActive ? 10 : 1,
                  background: isActive
                    ? `linear-gradient(180deg, ${hexToRgba(item.color, 0.18)} 0%, transparent 100%)`
                    : "transparent",
                }}
                onMouseEnter={() => handleThumbEnter(item.key)}
                onMouseLeave={handleThumbLeave}
              >
                {/* 微型色条 */}
                <div
                  className="w-10 h-1 rounded-full flex-shrink-0"
                  style={{ background: item.color }}
                />

                {/* 标签 */}
                <span
                  className="text-xs font-medium text-center leading-tight"
                  style={{ color: isActive ? item.color : "hsl(var(--muted-foreground))" }}
                >
                  {item.label}
                </span>

                {/* 材质牌号 */}
                <span className="text-[10px] font-mono text-fpso-dim">
                  {item.material}
                </span>

                {/* 占位标记 */}
                {item.placeholder && (
                  <span className="text-[9px] text-fpso-orange/70 absolute bottom-1.5">
                    坐标待标定
                  </span>
                )}

                {/* 数据就绪标记 (非占位 + 非激活时显示小绿点) */}
                {!item.placeholder && !isActive && (
                  <span className="absolute top-1 right-1.5 w-1.5 h-1.5 rounded-full bg-fpso-green/60" />
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
