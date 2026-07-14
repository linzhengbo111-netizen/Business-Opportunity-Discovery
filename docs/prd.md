# 需求文档


## 1. 应用概述

### 1.1 应用名称

Business Opportunity Discovery

**副标题**：Stainless Steel Opportunity Tracking in Global FPSO Projects

### 1.2 应用描述

一个专业的深色数据终端风格网页界面，用于展示全球 FPSO（浮式生产储卸油装置）项目信息。界面采用高级、极简、科技感设计，提供全球项目分布地图、项目列表展示、国家筛选等功能。本期仅实现前端 UI 和交互，不包含后端功能。

本系统聚焦于 **FPSO 项目中涉及不锈钢材料的需求与商机**，旨在帮助不锈钢行业（板材、管材、焊材、设备制造商等）快速发现全球 FPSO 建造、改装、维修项目中可能用到不锈钢的环节。爬取的原始数据虽来源于油气行业公开信息，但最终呈现和分析维度均围绕不锈钢应用展开。

## 2. 用户与使用场景

### 2.1 目标用户

**不锈钢行业市场分析人员、不锈钢供应链商机挖掘人员**

### 2.2 核心使用场景

用户访问网页查看全球 FPSO 项目分布情况、浏览项目列表、按国家筛选项目、查看项目详细信息及数据来源

## 3. 页面结构与功能说明

### 3.1 页面结构

```
全球FPSO项目商机挖掘系统（单页面）
├── 顶部导航栏（粘性定位）
├── 全球分布地图展示区域
├── 项目列表展示区域
└── 页脚
```

### 3.2 整体设计规范

#### 3.2.1 配色方案

* 背景色：#0a0f1e
* 面板/卡片：#131a2e
* 边框：#1e2844
* 主强调色（霓虹蓝）：#00d4ff，用于高亮、发光效果、按钮、边框
* 辅助色（琥珀橙）：#ff9f43，用于警告/待定状态

#### 3.2.2 字体规范

* 常规文字：无衬线字体（如 Inter）
* 数字：等宽字体

#### 3.2.3 设计风格

* 深色数据终端风格
* 大量留白
* 细线分割
* 排版极简

### 3.3 顶部导航栏

#### 3.3.1 左侧标题

* 显示文字：「Business Opportunity Discovery」
* 颜色：#00d4ff
* 字体：略大加粗
* 效果：带发光效果

#### 3.3.2 中间导航链接

* 包含三个链接：Dashboard、Database、Settings
* 当前页面（Dashboard）高亮显示（**本期交互说明**：Dashboard、Database、Settings 三个导航链接本期仅作为 UI 视觉占位，点击后无页面跳转或数据加载功能，无需绑定任何 JavaScript 点击事件。）
* “三个链接使用 \`\` 标签但 `href="javascript:void(0)"` 或不设 `href`，同时通过 CSS 禁止鼠标指针变为手型（如 `cursor: default`），以强调纯展示用途。”

#### 3.3.3 右侧区域

* **国家筛选下拉框**

  * 标签文字：「Region」
  * 下拉框 id：`country-select`
  * 样式：半透明深色背景，1px #00d4ff 边框，文字白色
  * **⚠️ 下拉选项生成规则（重要）**：为保证筛选器与数据 100% 匹配，下拉框内的 ``列表**不得在 HTML 中写死**。必须通过 JavaScript 读取 3.5.4 中的静态示例数据，自动提取所有 `country` 字段并去重，动态生成选项列表。选项首位固定为 `All Countries`（全选），其余国家选项按英文名称字母升序排列（例如 Angola → Brazil → Côte d'Ivoire → Guyana → Nigeria → UK）。**选项显示格式**：每个`` 的 `textContent` 必须包含国旗 emoji 和国家名称，格式为 `🇧🇷 Brazil`。“国旗 emoji 可从该国**任意一个 `flag` 字段非空的项目**中获取（建议取第一个含 flag 的项目）；若该国所有项目均无 `flag` 或值为空，则该选项仅显示国家名称，不显示 emoji。”选项的 `value` 属性仍为纯国家名称，以便与 `country` 字段全等匹配。
  * **覆盖要求**：当前 3.5.4 静态示例数据中出现的国家（如 Brazil、Guyana、Angola、Nigeria、UK、Côte d'Ivoire）必须全部能被该动态机制自动包含在内，不允许出现“数据里有科特迪瓦，下拉框却选不到”的情况。**特殊字符排序规范**：由于数据中包含 `Côte d'Ivoire` 等带有变音符号的国家名称，JavaScript 排序时**必须使用 `localeCompare(undefined, { sensitivity: 'base' })`** 方法（例如 `countries.sort((a, b) =&gt; a.localeCompare(b, undefined, { sensitivity: 'base' }))`），以确保特殊字符与普通字母按同一基准排序，避免出现 `Côte d'Ivoire` 被排到列表末尾的情况。同时，在下拉框 `value` 赋值和地图坐标 Key 匹配时，**必须使用 `===` 全等比较，并先对字符串执行 `.trim()`**，防止因首尾空格导致匹配失败，从 `projects` 中提取 `country` 时，必须对每个值执行 `.trim()`；生成 `option` 的 `value` 也使用 trim 后的值。
  * 该逻辑在验收标准中也应体现，确保下拉框里出现的国家名和列表数据中的完全一致。
  * “若该国所有项目均无 `flag` 字段或值为空，则该选项仅显示国家名称，不显示 emoji。”
* 实时更新指示器或时间戳占位（右上角小型显示）右上角显示一个小型 LIVE 指示灯（绿色圆点 + “LIVE” 文字，带呼吸动画），表示数据实时更新状态。本期 LIVE 指示灯仅作为视觉装饰元素，不反映真实的数据连接状态，无交互逻辑。

**后期扩展注意**：当前 LIVE 为纯装饰。后期对接真实数据后，应将 LIVE 状态与后端数据时间戳联动：若最新数据更新时间超过 24 小时，指示灯由绿色变为灰色，文字改为“STALE”。本期无需实现，但需预留 CSS 样式类（如 `.live-stale`）以便后期切换。

#### 3.3.4 定位方式

粘性定位，始终固定在页面顶部

### 3.4 全球分布地图展示区域

#### 3.4.1 地图背景

* 使用深色世界地图轮廓作为背景（CSS 绘制或 SVG 占位）使用深色世界地图轮廓作为背景（推荐使用等矩形投影的 SVG 轮廓图，如一个简化的 world.svg，置于容器内），风格：数据仪表盘样式。若使用 SVG，可将其作为 \`\` 或内联 SVG，**补充约束：** 地图背景必须使用 SVG 矢量格式文件，并通过 CSS 设置为 `width: 100%; height: auto;`，以确保容器缩放时光点的百分比定位始终与地图轮廓几何吻合，避免因位图缩放失真导致光点偏移。确保不影响坐标百分比定位。提供的 `world.svg` 自身宽高比必须为 **2:1**（推荐尺寸 1000×500 px），以确保在 `aspect-ratio: 2/1` 的容器内完全贴合，避免光点坐标偏移。若无法提供 2:1 的 SVG，则需改用 `object-fit: cover` 或调整坐标映射表，但本期推荐直接使用标准比例素材。
* 风格：数据仪表盘样式
* “SVG 文件路径暂定为 `assets/world.svg`，由设计提供；开发阶段可先用一个占位 SVG 或 Base64 内联，确保坐标百分比布局可调通。”
* **3.4.1.1 地图投影与坐标基准**
* 地图背景采用等矩形投影（Equirectangular）世界轮廓图，置于固定宽高比的容器内（建议 1000×500 px 或等比缩放）。`3.4.5` 中的坐标映射表的 x/y 值均基于此投影，以容器宽高百分比计算。若替换背景图，需保证投影一致，否则光点位置会偏移。**容器约束**：地图容器必须设置固定宽高比 `2:1`，例如使用 CSS `aspect-ratio: 2/1`，并设定 `max-width: 1000px`，内部使用 `position: relative`。光点采用 `position: absolute`，通过 `left` 和 `top` 百分比定位，以确保在不同视口宽度（≥1280px）下位置不变。

#### 3.4.2 项目位置标记

* 地图上的发光蓝色圆点**必须基于 3.5.4 中的静态示例数据动态生成**。渲染逻辑为：读取 `projects` 数组，提取所有唯一的 `country` 字段，为每个国家在地图对应位置生成一个圆点。
  **定位方式**：采用一个预定义的“国家-坐标”映射表（见下方补充说明），圆点根据映射表中的坐标放置。若某国家在映射表中无坐标，则不显示光点（或采用默认隐藏处理），确保页面不会报错。
  **光点数量**：与数据中出现的国家数量一致（当前示例数据为 6 个国家：Brazil, Guyana, Angola, Nigeria, UK, Côte d'Ivoire）。
* 圆点效果：脉冲动画（CSS animation）。页面加载时，各光点**依据 3.4.5 坐标映射表中的 `x` 值（代表经度）从大到小（即从东向西）依次出现**。“JavaScript 必须先从去重后的国家数组中**过滤出在 `countryCoordinates` 中存在映射坐标的国家**，然后将过滤后的国家数组按 `countryCoordinates[country].x` 进行降序排序（`sort((a,b) =&gt; b.x - a.x)`），然后按排序后的顺序渲染光点。**第一个光点的 `animation-delay` 设为 `0s`，第二个设为 `0.2s`，第三个 `0.4s`，后续依次递加 0.2 秒**，营造数据从东半球向西半球实时接入的视觉感受。”
* **动画兼容性要求**：光点使用 `animation` 实现脉冲和依次出现，必须设置 `animation-fill-mode: backwards` 以保证动画开始前元素不可见，延迟后渐显。光点一经渲染即可响应点击事件（即使处于动画延迟期间，只要元素存在于 DOM 中就可以点击）。需确保点击事件绑定不受动画延迟影响。
* 如果某个国家在坐标映射表中不存在，该国的项目不会在地图显示光点，但其项目仍然出现在列表中，且统计数字不变。控制台不报错。

#### **3.4.3 统计数据展示**

* **位置**：地图下方
* 显示内容：总计（Total）、在建（Active / Under Construction）、规划（Planned）三类统计数据。
  **统计规则定义**：
  * `Total` = 数组 `projects` 的总长度
  * `Active` = `status === "Under Construction"` 的项目数量
  * `Planned` = `status === "Planned"` 的项目数量
    （`Delivered` 状态的项目仅计入 `Total`，不单独建分类统计。）
    * **字体**：大号等宽字体
    * **布局与防抖规范**：三个统计卡片（Total / Active / Planned）必须采用 Flex 或 Grid 等宽布局，数字部分强制使用等宽字体（如 JetBrains Mono 或 Courier New）并**右对齐**。每个统计数字的容器需设置 `min-width: 100px`，预留至少 4 位数字的宽度，以防止未来数据量从 7 增长到 127 时，数字跳动导致相邻文字错位。容器设置 `flex-shrink: 0` 以防止被压缩；当数字超过 4 位（如 1000+）时，宽度应能自动扩展，不挤压相邻文字。三个数值元素分别使用 id：`stat-total`、`stat-active`、`stat-planned`

**3.4.4 地图标记交互逻辑（为后续功能预留前端接口）**

* **交互行为**：用户鼠标点击地图上任意一个**由数据动态生成的发光蓝色圆点**时，页面需绑定 `click` 事件并执行以下交互动作（为后期对接真实数据预留接口）：
  1. **联动下拉框**：顶部导航栏右侧的 `Region` 下拉框（id 为 `country-select`）自动切换至该光点对应的国家选项。并在切换下拉框 `value` 后，必须使用 `document.getElementById('country-select').dispatchEvent(new Event('change', { bubbles: true }))` 手动触发该下拉框的 `change` 事件，以便后期开发者只需监听 `change` 事件即可无缝实现列表筛选，无需再额外处理地图点击逻辑。
  2. **联动列表占位**：虽然本期不强制实现真实筛选，但事件函数中必须包含 `console.log` 调试输出，格式为 `"Clicked on {country}, ready to filter list"`（例如 `"Clicked on Brazil, ready to filter list"`）。多项目国家需包含项目数量，格式为 `"Clicked on {country} ({count} projects), ready to filter list"`，方便后续开发人员无缝对接真实的列表过滤逻辑。
* **设计意图**：确保后期接入爬虫数据时，用户点击地图能立刻联动筛选器，无需再修改前端 HTML 绑定代码。
* **多项目国家的行为说明**：
  当一个国家有多个项目时（如 Brazil 有 2 个项目），地图上仍只显示一个光点。后期点击该光点并联动下拉框筛选后，项目列表应显示该国的**所有项目**。本期 console.log 输出内容可包含项目数量提示（例如 `"Clicked on Brazil (2 projects), ready to filter list"`）。
* **实现细节补充**：渲染每个地图光点时，必须为该光点的 DOM 元素设置 `data-country` 属性，属性值为对应的国家名称（与 `country` 字段全等）。示例：\`\`。点击事件中通过 `e.currentTarget.dataset.country` 获取国家值，并用于联动下拉框。
* “项目数量可通过 `projects.filter(p =&gt; p.country === country).length` 获取。”

#### 3.4.5 国家地图坐标映射表（供 3.4.2 光点定位使用）

为保证地图光点准确落在对应国家位置，前端 JavaScript 必须维护一个包含 `x`（水平百分比）和 `y`（垂直百分比）的映射对象。`x` 值从左到右代表经度从西到东，`y` 值从上到下代表纬度从北到南。

**硬性编码要求**：该映射表的 Key 必须与 `projects` 数据中的 `country` 字段 **完全一致（区分大小写和特殊字符）**。

```javascript
const countryCoordinates = {
  "Brazil": { x: 45, y: 78 },        // 南美洲东部
  "Guyana": { x: 35, y: 58 },        // 南美洲北部
  "Angola": { x: 62, y: 82 },        // 非洲西南部
  "Nigeria": { x: 58, y: 70 },       // 非洲西部
  "UK": { x: 48, y: 35 },            // 欧洲西部
  "Côte d'Ivoire": { x: 55, y: 65 }  // 非洲西部（注意特殊字符 ô, è）
};
```

---

### 3.5 项目列表展示区域

#### 3.5.1 容器设置

* 容器 id：projects-container
* 用途：用于后续 JavaScript 动态渲染
* 容器内必须硬编码一个空状态提示元素（`No projects found for this region.`），默认隐藏。当筛选后无结果时，JavaScript 显示该提示。

#### 3.5.2 列表样式

* 卡片式设计，非传统表格
* 行背景：透明
* 行间分隔：极细的深色线
* 鼠标悬停效果：
  * 行背景轻微变亮
  * 内容向右平移 2px
  * 过渡动画流畅

#### 3.5.3 每行项目信息结构

* 项目名称：加粗，左侧显示
* 国家标签：小标签，深色背景 + 国旗 emoji+ 国家名
* 状态指示：发光小圆点 + 文字

  * 在建：蓝色圆点
  * 交付：绿色圆点
  * 规划：橙色圆点
* 简介摘要：一行灰色文字，通过 CSS `text-overflow: ellipsis` 单行省略，最多显示约 60 个英文字符，超出部分以“...”截断。**不锈钢信息标签（预留）**：当数据中的 `stainlessSteel` 或 `application` 非空时，在项目名称下方显示小型标签（如 `316L`、`Cargo Oil Tanks`）。本期示例数据这两个字段均为空字符串，但对应的 ``占位元素必须在渲染模板中硬编码，并默认隐藏。后期数据赋值后可直接显示。当 `stainlessSteel` 与 `application` 同时非空时，应分别渲染为两个独立标签，而非合并为一个。`stainlessSteel` 标签使用 class `tag-ss-grade` 展示牌号（如 `316L`），`application` 标签使用 class `tag-ss-app` 展示应用部位（如 `Cargo Oil Tanks`）。两者在渲染模板中均预留独立的`` 元素，各自根据字段是否为空控制显隐。“渲染时若字段值为空字符串，为该 \`\` 添加 `hidden` 属性或 CSS 类 `.tag-hidden { display: none; }`，确保不占据可见空间。”
* 在示例数据的 JS 对象里，每个项目确保有 `"stainlessSteel": "", "application": ""`。
* 本期项目名称及摘要文本区域不绑定任何点击事件，鼠标悬停仅保留行背景变亮和平移效果。后期如需进入详情页，推荐将整行设为可点击区域，并统一绑定 `click` 事件。
* “若 `status` 不在已定义的三种状态内，则显示灰色圆点，并在圆点后直接展示原始 `status` 文本，以保证信息不丢失。”
* 数据来源：

  * 蓝色可点击链接
  * 文字为来源网站名称
  * 必须带有 target="\_blank"
  * 显示小外部链接图标，链接文字后显示小外部链接图标，使用 Unicode 字符 `↗`（U+2197，即 `↗`），放置于链接文字后方，与文字之间无空格。可配合 CSS 设置 `font-size: 0.8em` 微调大小。
  * “鼠标悬停时，链接文字显示底部下划线（`text-decoration: underline`），外部链接图标 `↗` 不跟随下划线。”
  * **截断实现要求**：简介摘要的容器必须设置 `white-space: nowrap; overflow: hidden; text-overflow: ellipsis;`，并且通过父级弹性布局或固定宽度限制其最大宽度，防止超长文本撑开卡片。当前示例数据中的 Rosebank 项目摘要明显超过 60 字符，可用来验证截断效果。“若摘要容器位于弹性布局（`display: flex`）的子元素中，必须额外为该容器设置 `min-width: 0`，以确保 `overflow: hidden` 能正常截断文本，防止 flex 子元素溢出父级。”
  * 每个来源链接下方或右侧，应预留一行小字显示抓取日期（格式 `YYYY-MM-DD`）。本期所有示例统一显示为 `2026-07-17`，但 DOM 结构中必须有这个元素，以便后期动态更新。该行小字必须读取对应项目 `source.date` 字段的值进行渲染，不可在模板中硬编码日期字符串。

#### 3.5.4 静态示例数据

**⚠️ 单一数据源约束**：
`projects` 数组是本期所有动态渲染（列表、统计、下拉选项、地图光点）的**唯一数据源**。任何地方禁止硬编码与数据相关的数字、国家名称或状态计数，所有展示内容必须由此数组派生。

以下数组为开发时直接使用的标准数据结构，所有动态渲染（列表、统计数字、下拉选项、地图光点）均以此数据源为准。

```javascript
const projects = [
  {
    name: "FPSO Maria Quitéria",
    country: "Brazil",
    flag: "🇧🇷",
    status: "Under Construction",
    summary: "Petrobras pre-salt Santos Basin",
    source: { name: "Petrobras", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  },
  {
    name: "FPSO Prosperity",
    country: "Guyana",
    flag: "🇬🇾",
    status: "Delivered",
    summary: "ExxonMobil Stabroek block Payara",
    source: { name: "SBM Offshore", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  },
  {
    name: "FPSO Agogo",
    country: "Angola",
    flag: "🇦🇴",
    status: "Under Construction",
    summary: "MODEC EPC contract for TotalEnergies",
    source: { name: "MODEC", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  },
  {
    name: "FPSO Zafiro",
    country: "Nigeria",
    flag: "🇳🇬",
    status: "Planned",
    summary: "Replacement for aging FPSO",
    source: { name: "World Oil", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  },
  {
    name: "FPSO Rosebank",
    country: "UK",
    flag: "🇬🇧",
    status: "Planned",
    summary: "Equinor's major North Sea development project featuring advanced subsea production   systems and stainless steel topside modules",
    source: { name: "Offshore Energy", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  },
  {
    name: "FPSO Atlanta",
    country: "Brazil",
    flag: "🇧🇷",
    status: "Under Construction",
    summary: "Enauta's Santos Basin project",
    source: { name: "Offshore Magazine", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  },
  {
    name: "FPSO Baobab",
    country: "Côte d'Ivoire",
    flag: "🇨🇮",
    status: "Planned",
    summary: "FEED phase targeting 2028 startup",
    source: { name: "Offshore Energy", url: "https://example.com", date: "2026-07-17" },
    stainlessSteel: "",
    application: ""
  }
];
```

#### **未来扩展字段预留**：为后续对接不锈钢行业爬虫数据，`projects` 数组中的每个对象建议预留以下字段（本期可不赋值或设为空字符串）：

* `stainlessSteel`: 涉及的不锈钢牌号（如 `"316L"`, `"Duplex"`）
* `application`: 不锈钢应用部位（如 `"Cargo Oil Tanks"`, `"Process Piping"`）

本期示例数据中，这些字段可统一设为 `""` 或省略，但不影响前端渲染。后期只需在列表中展示这些字段即可，无需大改数据结构。

#### 3.6 页脚

#### 3.6.1 左侧文字

「Data aggregated from public sources. For internal analysis only.」

* 颜色：灰色小字

#### 3.6.2 右侧文字

* 右侧显示「Last updated: 」+ 当前日期。**本期实现方式**：由于无后端接口，该日期由 JavaScript 在页面加载时通过 `new Date().toISOString().slice(0,10)` 自动获取浏览器本地当日时间并渲染。**后期对接后端后**，改为读取后端返回的最新数据更新时间戳。

#### 3.6.3 分隔线

上方用一条淡灰色细线分隔

## 4. 业务规则与逻辑

### 4.1 国家筛选交互

* 用户通过下拉框选择国家时，界面需支持后续 JavaScript 动态筛选项目列表
* 下拉框 id 为 country-select，便于 JavaScript 控制
* **本期实现范围说明**：
  本期的下拉框 `change` 事件只绑定 `console.log` 输出，格式为 `"Region changed to: {country} ({count} projects)"`（例如 `"Region changed to: Brazil (2 projects)"`）。当选择“All Countries”时，输出 `"Region changed to: All Countries"` 并显示总项目数。，**不触发项目列表的筛选或重渲染**。此绑定旨在验证交互链路畅通，为后期接入真实筛选逻辑预留监听入口。后期开发者可直接在 `change` 事件中添加筛选函数即可生效。

### 4.2 项目列表动态更新

* 项目列表容器 id 为 projects-container，便于 JavaScript 动态渲染
* 统计数字需支持通过 id 修改

### 4.3 外部链接跳转

* 所有数据来源链接必须在新标签页打开，并附加 `rel="noopener noreferrer"`（即 `target="_blank" rel="noopener noreferrer"`）。

## 5. 异常与边界情况

| 场景                 | 处理方式                                       |
| -------------------- | ---------------------------------------------- |
| 鼠标悬停项目行       | 行背景轻微变亮，内容向右平移 2px，过渡动画流畅 |
| 点击数据来源链接     | 在新标签页打开外部链接                         |
| 页面滚动             | 顶部导航栏保持粘性定位，始终可见               |
| 地图无对应坐标的国家 | 项目列表正常展示，地图不显示光点，无错误提示。 |
| 筛选后无匹配项目     | 列表区域显示占位提示文字，地图不受影响。       |

## 6. 验收标准

1. 用户打开网页，看到深色数据终端风格界面，包含顶部导航栏、全球地图、项目列表、页脚
2. 用户观察全球地图区域，看到巴西、安哥拉、圭亚那、尼日利亚、英国附近的蓝色脉冲圆点，地图下方显示统计数据（总计、在建、规划）。这些统计数据必须通过 JavaScript 遍历下方项目列表中每条数据的 `status` 字段动态计算得出，且与当前展示的 7 条示例数据的状态严格一一对应（即：统计数字 = 对 7 条数据按状态分组计数后的结果，严禁在 HTML 中写死为「Total Projects: 15 | Active: 9 | Planned: 4」）“用户观察地图加载过程，蓝色圆点从右侧（东半球）向左侧（西半球）依次出现，每个光点间隔约 0.2 秒。”
3. 用户浏览项目列表，看到 7 个静态示例项目，每个项目包含名称、国家标签、状态指示、简介、数据来源链接
4. 用户鼠标悬停某个项目行，看到行背景变亮且内容向右平移 2px 的流畅动画效果
5. 用户点击任意项目的数据来源链接，链接在新标签页打开
6. 用户向下滚动页面，顶部导航栏保持固定在页面顶部
7. 显示浏览器当前日期，格式为 YYYY-MM-DD」，并明确示例（如 `Last updated: 2026-07-17` 仅为当前日期的一种可能）
8. 用户点击顶部导航栏右侧的「Region」下拉框，看到下拉选项已自动包含所有 7 条示例数据中涉及的国家（必须包含 Brazil、Guyana、Angola、Nigeria、UK 等，且与数据中的 `country` 字段完全匹配），选项列表首位固定为「All Countries」，其余国家按字母顺序排列。整个过程无需开发人员在 HTML 中手动硬编码维护 \`\` 列表
9. 用户点击地图上任意发光圆点（例如巴西光点），顶部导航栏的「Region」下拉框自动切换为对应的国家名称（例如切换到「Brazil」），同时浏览器开发者工具的控制台（Console）中有对应的调试日志输出（例如输出 `"Clicked on Brazil, ready to filter list"`），为后续对接真实筛选逻辑预留了清晰的交互接口
10. **不锈钢预留标签验证**：用户查看项目列表时，每条项目名称下方**看不到**任何不锈钢牌号或应用部位的标签（因示例数据 `stainlessSteel` 和 `application` 均为空字符串）。通过浏览器开发者工具检查对应 DOM，可以确认 \`\` 占位元素已存在且通过 CSS 隐藏（如 `display: none` 或 `hidden` 属性），确保后期数据填充后可立即显示。

## 7. 本期不实现功能

**⚠️ 特别说明（必读）：**

以下列出的「不实现」特指**不与后端真实爬虫数据联动**的完整业务逻辑。但基于 7 条静态示例数据的**初次页面渲染（统计数字计算、下拉选项生成、项目列表展示）** 以及**点击地图光点联动下拉框切换并输出 console.log 调试日志**，属于第 6 章验收标准中已明确要求实现的范围，必须在本期完成。

* 后端数据存储与管理
* 真实后端 API 的数据加载与对接
* 基于用户选择国家后，调用后端接口重新获取数据并刷新项目列表的完整筛选逻辑
* 基于后端 API 返回数据的项目列表刷新逻辑（本期仅基于前端静态示例数据进行初次渲染）
* 基于 WebSocket 或轮询方式的统计数字实时推送更新（本期仅基于静态数据进行初次计算）
* “基于项目真实经纬度坐标的地图光点动态定位（本期使用预定义的 `countryCoordinates` 映射表按国家放置光点，不根据每个项目的实际经纬度计算位置；光点数量和数据中的国家数量动态关联，并非固定装饰）”
* 用户登录与权限管理
* 数据导出功能
* 项目详情页面（弹窗或独立页）
* 搜索功能
* 排序功能（如按名称、状态、日期排序）
* 分页功能

**8. 假设与限制**

* 本期前端仅针对桌面端浏览器（视口宽度 ≥ 1280px）进行设计与优化，不实现移动端响应式布局。
* 地图背景及坐标基于等矩形投影，若背景图更换需同步调整坐标映射表。
