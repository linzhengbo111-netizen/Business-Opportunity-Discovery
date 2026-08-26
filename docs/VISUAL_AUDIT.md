# 商机挖掘系统 · 视觉审计报告

**日期**: 2026-08-26
**范围**: 全站 UI（Dashboard / Database / 战报中心 / 项目时间线 / 行业拆解 / Review / Settings 及全部 dashboard 组件）
**方式**: 静态代码审计（未改任何代码），所有结论附文件:行号，所有建议可直接执行。
**符号**: ⚡ = 高性价比优化点（投入小、提升大）

---

## 总评

系统已有一套设计意图良好的浅色数据终端体系（`fpso.*` 色板、HSL CSS 变量、shadow 四级 token、渐变标题、地图呼吸灯），但执行层存在三大系统性问题，导致"高级感"被细节拖垮：

1. **深色模式是幽灵模式**。`darkMode: ['class']` 已配置、`next-themes` 已安装、shadcn chart 有 `.dark` 主题分支——但全项目没有任何代码把 `.dark` 挂到 `<html>` 上，`index.css` 也没有 `.dark` 变量块。深色模式从机制到 token 全部缺失，业务页面 0 个 `dark:` 变体。当前"两个主题"实际只有浅色一个。
2. **颜色双轨制**。同一语义多个色值并存：主色是 `#0284c7`，地图光点却是 `#3b82f6`；同一个阶段，进度条分段是 `#f97316`、徽章却是 `#ea580c`；同一 LIVE 状态，一页翠绿一页深绿；另混入 amber-400/yellow-400/pink-400 等色板外颜色。整体色温漂移，纯度/饱和度不统一。
3. **同屏语义冲突**。同一条数据（推荐材质/推荐产品）在 PushAnalysisPanel 与 BattleCard 中颜色编码互相矛盾，且两组件同屏并排。

另有大量"小洞"：字体声明了没加载、3 个静默失效的类、加载态三种语言、时间线连接线错位 3px 等。逐项如下。

---

## P0 — 系统性缺陷（建议优先修复）

### P0-1 深色模式完全失效：机制 + token 双重缺失

**证据链**：
- [tailwind.config.js:6](tailwind.config.js#L6) 配置 `darkMode: ['class']`，要求 `<html>` 上有 `.dark` 类。
- `package.json` 装了 `next-themes@0.4.6`，但全 src 搜不到任何 `ThemeProvider` mount；[App.tsx:14](src/App.tsx#L14) 只包了 `AuthProvider`。没有 Provider，`.dark` 永远不会被加。
- [index.css](src/index.css) 全文（275 行）只有 `:root` 浅色变量，**没有 `.dark { }` 块**。
- src 共 77 个 tsx，只有 7 个文件用了 `dark:` 前缀（5 个 ui 原语 + AuthCallbackPage + NotFound），全部业务页面与 dashboard 组件 0 个 dark 变体。
- [chart.tsx:7](src/components/ui/chart.tsx#L7) `THEMES = { light: "", dark: ".dark" }` 指向一个不存在的 token 块。
- [BattleCard.tsx:6](src/components/dashboard/BattleCard.tsx#L6) 注释自称 "Dark terminal theme matching the app"，是过期注释，实际渲染浅色。

**建议**（二选一，推荐方案 A）：
- **方案 A（完整）**：在 [index.css](src/index.css) 补 `.dark` 变量块（背景 `#0b1220` 系、卡片 `#111a2b` 系、主色提亮为 `#38bdf8`、边框 `#1e293b`、文字 `#e2e8f0` / `#94a3b8`）；mount next-themes `ThemeProvider attribute="class"`；`fpso.*` 色板从静态 hex 改为引用 CSS 变量。
- **方案 B（务实）**：产品层明确"仅浅色"，删除 [chart.tsx:7](src/components/ui/chart.tsx#L7) 的 `THEMES.dark` 分支与相关注释，避免误导审计与维护。

无论选哪条，都先决定，因为 P1/P2 大量"写死浅色"问题依赖此决策。

### P0-2 颜色双轨制：同一语义多个色值

| 语义 | 值 A | 值 B | 位置 |
|---|---|---|---|
| 主色蓝 | `#0284c7`（--primary / fpso.blue） | `#3b82f6`（blue-500，地图光点及光晕） | [DashboardPage.tsx:1252](src/pages/DashboardPage.tsx#L1252)、[index.css:138,169-174](src/index.css#L138) |
| 阶段橙 | `#f97316`（--warning，PHASE_HEX） | `#ea580c`（fpso.orange，徽章/圆点类） | [project_phase.ts:72-83 vs 94-160](src/lib/project_phase.ts#L72) |
| 成功绿 | `#059669`（--success / fpso.green） | `#10b981`（emerald-500，PHASE_HEX / Review 发光） | [project_phase.ts:185-197](src/lib/project_phase.ts#L185)、[ReviewPage.tsx:446](src/pages/ReviewPage.tsx#L446) |
| 预警黄 | `#facc15`（PHASE_HEX Procurement） | `yellow-400` / `amber-400` / `yellow-600`（散落各页） | [project_phase.ts:78](src/lib/project_phase.ts#L78)、[DashboardPage.tsx:1173](src/pages/DashboardPage.tsx#L1173)、[DatabasePage.tsx:508](src/pages/DatabasePage.tsx#L508) |
| LIVE 绿 | `bg-emerald-400`（战报中心） | `bg-fpso-green` + live-breath（Dashboard） | [BattleCardsPage.tsx:322](src/pages/BattleCardsPage.tsx#L322) vs [DashboardPage.tsx:1082-1095](src/pages/DashboardPage.tsx#L1082) |

**建议**：
1. 建立唯一色源：阶段色只从 `project_phase.ts` 的 `PHASE_HEX` 出，`PHASE_HEX` 内部改引用 token 值（橙 `#ea580c`、绿 `#059669`、灰 `#64748b`、黄 `#facc15` 保留但必须在 [index.css](src/index.css) 注册为 `--chart-6` 或 `--warning-alt` 并注释用途）。
2. 地图光点三处（`bg-[#3b82f6]`、hover box-shadow、keyframes box-shadow）全部改 `#0284c7` / `rgba(2,132,199,x)`。⚠️ 这是全站最显眼的"两种蓝"。
3. 删除色板外 `yellow-400`、`amber-400`、`pink-400` 的使用（具体位置见 P1）。

### P0-3 同屏颜色语义冲突：推荐材质 / 推荐产品

**问题**：[PushAnalysisPanel.tsx:90,109](src/components/dashboard/PushAnalysisPanel.tsx#L90) 推荐材质=蓝、推荐产品=橙；[BattleCard.tsx:241,278](src/components/dashboard/BattleCard.tsx#L241) 推荐材质=绿、推荐产品=蓝。两组件同屏并排时，同一内容两种颜色编码，用户认知混乱。

**建议**：全局统一语义——**材质=蓝（`bg-fpso-blue/10 text-fpso-blue`）、产品=橙（`bg-fpso-orange/10 text-fpso-orange`）、绿只留给成功/下一步行动**。改 [BattleCard.tsx:241](src/components/dashboard/BattleCard.tsx#L241) 的绿为蓝即可（2 行改动，⚡）。

---

## P1 — 页面级可见问题

### 项目时间线（ProjectTimelinePage）

**P1-1 连接线不穿过圆点圆心（全场最显眼硬伤）** ⚡
[ProjectTimelinePage.tsx:693](src/pages/ProjectTimelinePage.tsx#L693)：竖线 `left-[15px]`，圆点 `h-3 w-3`（12px，圆心在 6px），线落在圆点右缘外侧 3px，连接关系错位。
```tsx
// 现状
<div className="absolute left-[15px] top-2 bottom-2 w-0.5 bg-fpso-border" />
// 建议
<div className="absolute left-[5px] top-2 bottom-2 w-0.5 bg-fpso-border" />
```

**P1-2 类别色定义三份且已漂移**
[ProjectTimelinePage.tsx:72-78 / 89-98 / 100-109](src/pages/ProjectTimelinePage.tsx#L72)：常量表、`timelineDotColor`、`timelineDotStyle` 三份定义，REGULATORY 一处 `bg-pink-400` 一处 `#db2777`。且 pink 不在任何 token 中，"监管/许可"（许可获批、同意书）读作桃红=危险色，语义错误。
**建议**：合并为单一 `CATEGORY_COLORS` 常量；REGULATORY 改 `#7c3aed`（violet）或 `#64748b`（slate）；删除未使用的 `timelineDotColor` 死代码。

**P1-3 筛选 chip 边框硬编码深藏青**
[ProjectTimelinePage.tsx:638](src/pages/ProjectTimelinePage.tsx#L638)：未激活态 `borderColor: "rgb(30 40 68 / 0.6)"`（比全站边框 #e2e8f0 深得多）+ 文字 `"#64748b"` 直写 hex。
**建议**：未激活态 `border-fpso-border text-fpso-muted`；激活态改 fpso 类名（`bg-fpso-green/15 text-fpso-green` 等）。

**P1-4 页面无主标题**
[ProjectTimelinePage.tsx:503,625](src/pages/ProjectTimelinePage.tsx#L503)：页面标签用 `text-[10px] uppercase tracking-wider`，主标题 "Timeline" 只是 `text-sm`，层级起点过低。Database/Review 筛选标签是 `text-xs font-medium` 小写。
**建议**：补 h1（`text-2xl font-semibold tracking-tight text-fpso-fg`），标签体系统一到 `text-xs font-medium`。

### Database

**P1-5 「待挖掘」徽章对比度 1.7:1 不可读** ⚡
[DatabasePage.tsx:508](src/pages/DatabasePage.tsx#L508)：`bg-amber-400/10 text-amber-400`——amber-400 文字在近白底上对比度约 1.7:1，10px 字号基本不可读，且 amber 不在 token 内。
**建议**：`bg-fpso-orange/15 text-fpso-orange ring-fpso-orange/20`（与页内其余徽章同体系）。

**P1-6 详情侧栏白玻璃叠黑遮罩发灰**
[DatabasePage.tsx:650](src/pages/DatabasePage.tsx#L650)：`bg-white/70 backdrop-blur-md` 叠在 `bg-black/60` 遮罩（643 行）上，70% 白 × 黑罩 = 灰浊面板，内容发暗。
**建议**：实色 `bg-fpso-card shadow-lift`，去掉 backdrop-blur（遮罩已有模糊）。

**P1-7 进度条轨道不可见 + 两套颜色编码**
[DatabasePage.tsx:872,932](src/pages/DatabasePage.tsx#L872)：轨道 `bg-fpso-bg`(#f8fafc) 画在 `bg-white/70` 卡片上几乎同色，空槽不可见；主评分条按 grade 变色（绿/蓝/橙/灰），5 个维度子条统一 `bg-fpso-blue/60`，同一区块两套编码。
**建议**：轨道改 `bg-fpso-border/50`；维度子条按 `dim.score / 20` 映射同款绿→蓝→橙→灰色阶。

**P1-8 中置信度=警告橙，语义过载**
[DatabasePage.tsx:53,55](src/pages/DatabasePage.tsx#L53)：confidence medium 用 `fpso-orange`，同一橙色还承担 grade C、Approval/EPC Award 阶段。中置信度渲染成警告色。
**建议**：medium 改 `bg-fpso-blue/15 text-fpso-blue`，橙只留给警告/热阶段。

### Dashboard

**P1-9 5 张统计卡三种 hover 组合** ⚡
[DashboardPage.tsx:1140-1207](src/pages/DashboardPage.tsx#L1140)：Total `hover:shadow-glow`、Early `hover:shadow-lift` + muted 灰边框（像禁用态）、Mid `yellow-400` 边框、Added 绿边框。
**建议**：统一 `hover:shadow-glow hover:-translate-y-0.5`，hover 边框色跟随各卡 accent（early→fpso-muted、mid→fpso-orange、late→fpso-blue、added→fpso-green）。

**P1-10 Mid 卡 yellow-400 非 token**
[DashboardPage.tsx:1173-1179](src/pages/DashboardPage.tsx#L1173)：`text-yellow-400 / hover:border-yellow-400/60 / bg-yellow-400/10`；且 Mid 组含 Approval/EPC Award（系统内为橙）+ Procurement（黄），用黄代表整组与阶段系统冲突。
**建议**：改 `fpso-orange` 全套。

**P1-11 环形图按排名着色，颜色随筛选漂移**
[DashboardPage.tsx:155-158,1298,1344](src/pages/DashboardPage.tsx#L155)：`fill={COUNTRY_CHART_COLORS[i]}`，i 是排序后索引——筛选一变，同一国家颜色就变。且 `#0c4a6e/#082f49/#0f172a` 三深色扇区互相不可辨，`#0f172a` 就是前景文本色；注释称"最深给最大扇区"，实际数据降序，i=0 拿到最浅色，注释与代码矛盾。7 个色全绕开 `--chart-1..5` token（token 定义后零消费）。
**建议**：建 `COUNTRY_COLOR: Record<string, string>` 按国家名固定映射，取色 `hsl(var(--chart-1))`…`hsl(var(--chart-5))`；`Other` 固定 `#94a3b8`。

**P1-12 地图光点出场延迟随数量线性增长**
[DashboardPage.tsx:1256-1257](src/pages/DashboardPage.tsx#L1256)：`animationDelay: index * 0.2s` 同时作用于入场动画和无限呼吸动画，30-50 国时最后一批光点 6-10 秒完全不可见，地图长时间空白。
**建议**：`Math.min(index * 0.2, 2)` 封顶；或拆两条 animation，delay 只给 fade-in-scale。

**P1-13 阶段条带霓虹光晕 + 黄条低对比**
[DashboardPage.tsx:1385-1393](src/pages/DashboardPage.tsx#L1385)：轨道 `bg-[#e2e8f0]`（= --border 值却硬编码）；每根条 `boxShadow: 0 0 8px ${color}66` 发光是装饰噪音；Procurement `#facc15` 黄条在白色卡片上对比度约 1.9:1。
**建议**：去掉 boxShadow 纯色填充；轨道 `bg-fpso-border`；黄改 `#ca8a04`（yellow-600）或 `--chart-2` 橙。

**P1-14 h1 用 slate-600，与战报中心不一致**
[DashboardPage.tsx:1127](src/pages/DashboardPage.tsx#L1127)：`text-slate-600`（#475569 不在设计系统）；[BattleCardsPage.tsx:313](src/pages/BattleCardsPage.tsx#L313) 用 `text-fpso-fg`。
**建议**：统一 `text-fpso-fg`。⚡

**P1-15 AI 分析中芯片两种写法 + amber 非 token**
[DashboardPage.tsx:389,457](src/pages/DashboardPage.tsx#L389)：389 无 ring、457 带 ring，两处 amber-400。另 [BattleCard.tsx:213](src/components/dashboard/BattleCard.tsx#L213) 还有第三处 `animate-pulse` 横幅。
**建议**：抽一个 `LoadingChip` 组件（`text-warning` 系）统一三处；loading 态统一方案见 P1-20。

### 组件层

**P1-16 全站硬编码 `bg-white/xx` 玻璃面板（暗色模式必坏点）**
位置：FilterSidebar:92、DatabasePage:368/457/650、Timeline:507/537/666/712/788、ReviewPage:362/366/375、BattleCardsPage:174、OutreachModal:108、Header:30、ThemeSelect:51。
**建议**：机械替换为 `bg-fpso-card/xx`（与 fpso.card 同值，但走 token，未来可挂 dark 变体）。⚡ 批量替换即可。

**P1-17 ThemeSelect 触发器硬编码白 + 与同行控件字号不一致**
[ThemeSelect.tsx:51](src/components/common/ThemeSelect.tsx#L51)：`bg-white/70`；且触发器 `text-xs`，而 DatabasePage:436 / ReviewPage:350 同行搜索输入 `text-sm`。
**建议**：触发器 `bg-fpso-card/70`；字号统一 `text-xs`（或全提 `text-sm`）。

**P1-18 FilterSidebar phase chip 内联 hex + 9.4% alpha + 黄字不可读**
[FilterSidebar.tsx:215](src/components/dashboard/FilterSidebar.tsx#L215)：`style={{ backgroundColor: \`${s.color}18\` }}`，Procurement `#facc15` 作文字白底对比度约 1.6:1。
**建议**：PHASE_HEX 黄改 `#ca8a04`；alpha 统一 `/10` `/15` 步进；移除内联样式改用 token 类。

**P1-19 FilterSidebar `writing-vertical` 静默失效**
[FilterSidebar.tsx:126](src/components/dashboard/FilterSidebar.tsx#L126)：Tailwind 无 `writing-vertical` 类，不生成 CSS，折叠态 "Filters" 横向渲染被 48px 容器裁切。
**建议**：`[writing-mode:vertical-rl]` 或删掉。

**P1-20 加载态三套语言并存**
PushAnalysisPanel:51 静态斜体文字、BattleCard:213 amber 脉冲横幅、OutreachModal:130 `animate-pulse` 文字、Timeline:661 纯文字、Database 蓝圈 spinner。五种呈现，无骨架屏。
**建议**：抽 `LoadingChip`（spinner + 文案，token 色）+ 列表用 [Skeleton](src/components/ui/skeleton.tsx) shimmer。中英文案统一（"Loading projects…" / "加载中…" 混用）。

**P1-21 `transition-all` 滥用（掉帧 + 动画观感杂乱）**
位置：FilterSidebar:92,208,238、FollowUpStatus:172、ThemeSelect:51、Header:69。侧栏宽度动画走 JS 内联 style + `transition-all` 会把布局属性纳入动画。
**建议**：侧栏 `transition-[width]`，chip/按钮 `transition-colors`。

**P1-22 Header 硬编码 + 登出红不达标**
[Header.tsx:30](src/components/common/Header.tsx#L30)：`bg-white/60` + 任意值阴影 `shadow-[0_1px_8px_rgba(15,23,42,0.04)]` → `bg-fpso-card/60 shadow-card`；[Header.tsx:94](src/components/common/Header.tsx#L94)：登出 `text-red-400`（白底对比 ~3.5:1 偏低且非 token）→ `text-destructive/80 hover:text-destructive`。

**P1-23 字体声明了但从未加载** ⚡
[index.css:90-94](src/index.css#L90)：`font-family: "Inter", "Glow Sans SC", …` 与 `.font-mono` 的 `"JetBrains Mono"` 全部无 @font-face、无 [index.html](index.html) link、无 fontsource import——**声明永远不生效，实际全部回退系统字体**。数字的等宽 tabular-nums 质感完全没兑现。
**建议**：`npm i @fontsource-variable/inter @fontsource/jetbrains-mono`，在 main.tsx import；Glow Sans SC 若无 npm 包，中文字体从系统栈兜底（保留声明无害）。这单个修复对"高级感"提升最大。

**P1-24 ReviewPage Follow 按钮发光硬编码 emerald**
[ReviewPage.tsx:446](src/pages/ReviewPage.tsx#L446)：`hover:shadow-[0_0_12px_rgba(16,185,129,0.3)]`（#10b981 非 token 绿）→ `hover:shadow-glow`。

**P1-25 ReviewPage 筛选 tab 激活态不醒目**
[ReviewPage.tsx:295-299](src/pages/ReviewPage.tsx#L295)：激活 `bg-fpso-blue/15 text-fpso-blue` 与 hover `bg-fpso-bg/50` 对比很低。
**建议**：激活态实色 `bg-fpso-blue text-white` 或加 `border-b-2 border-fpso-blue`；补 `focus-visible:ring-2 focus-visible:ring-fpso-blue/50`。

**P1-26 BattleCard 卡片阴影/圆角/backdrop-blur 三处不合规**
[BattleCard.tsx:173](src/components/dashboard/BattleCard.tsx#L173)：`shadow-2xl`（默认色板）+ `bg-fpso-card/60 backdrop-blur-md`（几乎不透明，blur 无效）+ `rounded-xl`（--radius 是 0.5rem，全站他处 rounded-lg）。
**建议**：`bg-fpso-card shadow-lift rounded-lg`，去 blur。

**P1-27 全局 button:hover 阴影波及所有按钮**
[index.css:74-79](src/index.css#L74)：`button { @apply shadow-sm } button:hover { box-shadow: var(--shadow-hover) }` 命中所有原生 button——模态关闭钮、时间线 tab、24px 幽灵按钮 hover 全出大阴影，与细小的 border/文字变色不匹配。
**建议**：删全局规则，阴影只留给 shadcn [Button](src/components/ui/button.tsx)。

---

## P2 — 打磨级问题

### 图表与数据可视化

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 2-1 | [chart.tsx:1-367](src/components/ui/chart.tsx) | 整文件死代码，全仓零 import，Dashboard 裸用 recharts | 要么 Dashboard 改用它（获得 token 化 tooltip），要么删除文件及 tailwind chart 配置 |
| 2-2 | [chart.tsx:241-244](src/components/ui/chart.tsx#L241) | `{item.value && …}` value=0 时数值列消失 | `item.value != null` |
| 2-3 | [DashboardPage.tsx:1306-1315](src/pages/DashboardPage.tsx#L1306) | tooltip 硬编码 hex + 无千分位 + 无占比 + 13px 字号 | `hsl(var(--popover))` / `var(--border)`；`value.toLocaleString()`；加 `(pct%)`；12px |
| 2-4 | [DashboardPage.tsx:1276-1279](src/pages/DashboardPage.tsx#L1276) | loading 期显示"无数据"误导文案 | `loading ? <Loading/> : empty ? <Empty/> : <Chart/>`（对齐地图区 1240 行分支） |
| 2-5 | [DashboardPage.tsx:1333](src/pages/DashboardPage.tsx#L1333) | 逐行 `Math.round` 百分比总和可能 ≠ 100% | 最大余数法，或 Other 行做差额修正 |
| 2-6 | [DashboardPage.tsx:1285-1305](src/pages/DashboardPage.tsx#L1285) | 扇区无 minAngle，小国扇区细到不可点；hover 蓝光不分扇区色 | `minAngle={2}`；`drop-shadow(0 0 6px currentColor)`（index.css:153） |
| 2-7 | [DashboardPage.tsx:1291-1293](src/pages/DashboardPage.tsx#L1291) | `paddingAngle={2}` 角形间隙对小扇区占比过大 | `stroke="var(--card)" strokeWidth={2}` 表面间隙 |
| 2-8 | [DashboardPage.tsx:1338-1340](src/pages/DashboardPage.tsx#L1338) | 图例禁用态仅改光标 | 加 `disabled:opacity-50` |
| 2-9 | [DashboardPage.tsx:1374](src/pages/DashboardPage.tsx#L1374) | Phase 条 2% 宽度下限造成 1 与 2 项目等长失真 | 去掉下限或改 0.5% |
| 2-10 | [DashboardPage.tsx:1401-1404](src/pages/DashboardPage.tsx#L1401) | 悬浮 tooltip 与右侧常显数值信息重复 | 删除悬浮层，或改成显示百分比 |
| 2-11 | [DashboardPage.tsx:1150-1217](src/pages/DashboardPage.tsx#L1150) | 指标卡大数字无千分位，详情表有，同页不一致 | 统一 `toLocaleString()` ⚡ |
| 2-12 | [IndustryBreakdownPage.tsx:67-74](src/pages/IndustryBreakdownPage.tsx#L67) | 2205 `#1d4ed8` 与 316L `#0284c7` 相邻且接近，idle 态 6% 透明度下不可辨 | 2205 改 `#4338ca` 拉开色相 |

### Database 表格

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 2-13 | [DatabasePage.tsx:462-464](src/pages/DatabasePage.tsx#L462) | 表头不吸顶、无斑马纹、hover 太弱（/5），10 列宽表易串行 | thead `sticky top-0 z-10 bg-fpso-card`；`odd:bg-fpso-bg/30`；`hover:bg-fpso-blue/10` |
| 2-14 | [DatabasePage.tsx:504,565](src/pages/DatabasePage.tsx#L504) | 项目名/摘要 truncate 后无 title 悬浮全文 | 补 `title={p.name}` |
| 2-15 | [DatabasePage.tsx:368,457](src/pages/DatabasePage.tsx#L368) | 静态工具栏/表格容器 `hover:shadow-lift` 悬停浮起暗示可点击 | 删这两处 hover:shadow-lift |
| 2-16 | [DatabasePage.tsx:695](src/pages/DatabasePage.tsx#L695) | Follow 按钮混用两套体系 `bg-fpso-blue` + `text-primary-foreground` | 统一 `bg-primary text-primary-foreground` |

### 时间线

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 2-17 | [ProjectTimelinePage.tsx:722-725](src/pages/ProjectTimelinePage.tsx#L722) | 事件徽章 `${dotColor}18`（9.4%）vs 全站徽章 /15（15%） | 统一 `${dotColor}26` |
| 2-18 | [ProjectTimelinePage.tsx:707](src/pages/ProjectTimelinePage.tsx#L707) | 圆点 50% 光晕在密集时间线发糊 | 降 `40` 或用 `--shadow-glow` |
| 2-19 | [ProjectTimelinePage.tsx:712](src/pages/ProjectTimelinePage.tsx#L712) | 不可展开卡有 hover 阴影但 `cursor-default`，反馈与行为不符 | 去 hover 阴影 |
| 2-20 | [ProjectTimelinePage.tsx:537](src/pages/ProjectTimelinePage.tsx#L537) | 下拉面板 `shadow-card`，ThemeSelect 用 `shadow-lift`，同类浮层不统一 | 统一 `shadow-lift` |
| 2-21 | [ProjectTimelinePage.tsx:661-664](src/pages/ProjectTimelinePage.tsx#L661) | 加载态纯文字，与 Database/Review spinner 不一致 | 复用 spinner + 文案 |

### 排版系统

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 2-22 | [tailwind.config.js:33,36](tailwind.config.js#L33) | `fpso.muted` 与 `fpso.dim` 同值 #64748b，两级语义无层级差 | dim 降为 `#94a3b8` |
| 2-23 | 各页 | 徽章三档字号混用：10px / 11px / text-xs | 统一 `text-[11px]` 或 `text-xs` 两档 |
| 2-24 | [DashboardPage.tsx:1908](src/pages/DashboardPage.tsx#L1908) | 同元素 `text-sm … text-xs` 冲突，实际生效取决于 CSS 生成顺序 | 只留 `text-xs` |
| 2-25 | [DashboardPage.tsx:426,432](src/pages/DashboardPage.tsx#L426) | 公司名/hullType 用 font-mono | mono 只用于数字/日期/牌号 |
| 2-26 | [ReviewPage.tsx:396-398](src/pages/ReviewPage.tsx#L396) | 日期普通比例字体，DatabasePage 同字段 font-mono | 补 `font-mono tabular-nums` |
| 2-27 | [DashboardPage.tsx:1122](src/pages/DashboardPage.tsx#L1122) vs [BattleCardsPage.tsx:309](src/pages/BattleCardsPage.tsx#L309) | 两页 py-10/py-8、section mb-8/mb-10 混排 | 统一 py-8 + mb-8 |

### 交互细节

| # | 位置 | 问题 | 建议 |
|---|---|---|---|
| 2-28 | [card.tsx:11](src/components/ui/card.tsx#L11) | shadcn Card 用默认 `shadow`，未用 `--shadow-card` token | `shadow-card` |
| 2-29 | [BattleCardsPage.tsx:174](src/pages/BattleCardsPage.tsx#L174) | 卡片无基础阴影偏平 + rounded-xl | `shadow-card rounded-lg` |
| 2-30 | [dropzone.tsx:48](src/components/dropzone.tsx#L48) | `border-gray-300` 绕 token | `border-border` |
| 2-31 | [GlobalSearch.tsx:72,92](src/components/dashboard/GlobalSearch.tsx#L72) | 输入文字用成功绿（语义冲突，绿已过载）；下拉 `shadow-2xl` | `text-fpso-fg` 保 font-mono；`shadow-lift` |
| 2-32 | [FollowUpStatus.tsx:175,215-252](src/components/dashboard/FollowUpStatus.tsx#L175) | 中性按钮 hover 用蓝色 shadow-glow；表单控件硬编码 bg-white | 只用 border/text 变色；`bg-fpso-card` |
| 2-33 | [index.css:263-265](src/index.css#L263) | select option 硬编码 #ffffff/#0f172a | 走 token 或留作浅色-only 声明 |
| 2-34 | [index.css:256-260](src/index.css#L256) | map-container max-width 1000px 左对齐，与下方全宽图表错位 | 加 `mx-auto` 或去 max-width |
| 2-35 | [DashboardPage.tsx:1247-1260](src/pages/DashboardPage.tsx#L1247) | 光点无名称提示，悬停不知国家 | 加 `title={dot.country}` |
| 2-36 | [DashboardPage.tsx:363-394](src/pages/DashboardPage.tsx#L363) | `border-current/20` 是静默失效类（Tailwind v3 不支持 currentColor 透明度修饰符），想要的同色淡边框从未生效 | 显式 `border-fpso-orange/20` 等或直接删 ⚡ |
| 2-37 | [DashboardPage.tsx:337](src/pages/DashboardPage.tsx#L337) + [index.css:204-212](src/index.css#L204) | `.project-row:hover` 背景声明被 utilities 层覆盖，死代码 | CSS 只留 translateX |
| 2-38 | [multi-select.tsx](src/components/ui/multi-select.tsx)、[NotFound.tsx](src/pages/NotFound.tsx) | 外来模板 token 泄漏：`text-title-md`、`shadow-theme-xs`、`gray-800` 等，是另一套设计系统 | 替换为 fpso/semantic token |
| 2-39 | [BattleCard.tsx:505-544](src/components/dashboard/BattleCard.tsx#L505) | 四个 action 按钮 hover 叠加全局 button:hover 大阴影 | 随 P1-27 修复 |
| 2-40 | [BattleCard.tsx:416-424](src/components/dashboard/BattleCard.tsx#L416) | footer 徽章重写 FollowUpStatus compact 逻辑，两处样式源 | 复用 FOLLOW_UP_STATUS_COLORS |
| 2-41 | [OutreachModal.tsx:98-108](src/components/dashboard/OutreachModal.tsx#L98) | 自定义弹窗无 role=dialog/aria-modal/Esc/焦点陷阱/滚动锁 | 接 shadcn Dialog 或补 a11y 四件套 |
| 2-42 | [FilterSidebar.tsx:136-139](src/components/dashboard/FilterSidebar.tsx#L136) | 折叠态仅 opacity+pointerEvents，键盘仍可 tab 进隐藏控件 | 折叠时 `inert` |
| 2-43 | [BattleCardsPage.tsx:317 vs 341](src/pages/BattleCardsPage.tsx#L317) | 空状态文案"A/B 级"与 `score >= 55` 逻辑不符（会纳入高分 C） | 改"暂无评分 ≥ 55 的商机项目" |
| 2-44 | [IndustryBreakdownPage.tsx:522,541](src/pages/IndustryBreakdownPage.tsx#L522) | emoji 标题（🎨📋）与全站 lucide 图标体系不一致 | 换 `Palette`/`Table2` 图标或纯文字 |
| 2-45 | [IndustryBreakdownPage.tsx:604-624](src/pages/IndustryBreakdownPage.tsx#L604) | 底部缩略块 div+纯 hover，触屏/键盘不可达 | 改 button + aria-pressed |
| 2-46 | [IndustryBreakdownPage.tsx:131,646-650](src/pages/IndustryBreakdownPage.tsx#L131) | "坐标待标定"分支永不触发（占位相关死代码与注释矛盾） | 删死代码或真正标记 intake 为 placeholder |
| 2-47 | [IndustryBreakdownPage.tsx:518](src/pages/IndustryBreakdownPage.tsx#L518) | 侧栏表格材质 chip 窄列换行 | `whitespace-nowrap` / `min-w-[64px]` |
| 2-48 | [ReviewPage.tsx:361-368](src/pages/ReviewPage.tsx#L361) | 空态纯文字无图标无"清除筛选"入口 | 补图标 + Clear filters 按钮 |

---

## ⚡ 高性价比优化清单（投入小、提升大，按性价比排序）

一天内可做完、视觉提升立竿见影：

1. **加载字体**（P1-23）：fontsource 装 Inter + JetBrains Mono，main.tsx 两行 import。全站数字质感和文字渲染即刻升级。
2. **时间线连接线**（P1-1）：`left-[15px]` → `left-[5px]`，1 行。全场最显眼的几何错误。
3. **地图光点统一主色**（P0-2）：`#3b82f6` → `#0284c7` 三处（tsx 1 处 + css 2 处）。两种蓝即刻消失。
4. **`bg-white/xx` 机械替换**（P1-16）：全局搜索替换为 `bg-fpso-card/xx`，约 15 处，纯文本替换无风险。
5. **`border-current/20` 清理**（2-36）：删除 3 处静默失效类，或改显式 `border-fpso-*/20`。顺带修好从未生效的徽章同色边框。
6. **amber-400 徽章换 token**（P1-5 / P1-15）：4 处，换 `fpso-orange`/`warning` 系，对比度从 1.7:1 提到 4.5:1+。
7. **统计卡 hover 统一**（P1-9）：一个样式片段复制 5 份。
8. **材质=蓝、产品=橙语义统一**（P0-3）：BattleCard 2 行。
9. **h1 颜色统一**（P1-14）：2 行。
10. **数字千分位统一**（2-11）：4 处 `toLocaleString()`。
11. **删全局 button:hover 阴影**（P1-27）：2 行 CSS，全站小按钮观感立即变干净。

---

## 附录：建议的 token 治理基线（修复后长期约束）

- **一个语义一个色值**：阶段/状态色只从 `project_phase.ts` 常量出；图表类别色只从 `--chart-1..5` 出；地图/装饰蓝只从 `--primary` 出。新增颜色必须在 [index.css](src/index.css) 注册并注释用途（如黄 `#facc15` → `--chart-6`）。
- **浅色面板色只走 `fpso-card` / `bg-card`**，禁止裸 `bg-white`。
- **阴影只走 token**：`shadow-card`（静态卡）→ `shadow-lift`（浮层/模态）→ `shadow-hover`（可交互卡 hover）→ `shadow-glow`（accent 卡）。禁止 `shadow`/`shadow-2xl`。
- **动效约定**：hover 颜色变化 150ms；阴影/位移 200ms；进场 fade-in-scale 500ms。禁止 `transition-all`。
- **徽章字号两档**：`text-[11px]` / `text-xs`，禁 10px 以下。
- **mono 只用于数字/日期/牌号**，不用于公司名等自然语言。
- **决策先行**：深色模式修（方案 A）还是明确砍（方案 B），必须在下一轮改动前拍板，P1-16 等一批替换的写法依赖此决策。
