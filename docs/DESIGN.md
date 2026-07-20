# Theme Name: 暗黑极简
# Vibe & Description: 在深色基底下刻意降低信息密度，以留白和节奏感拉开内容关系，主要依靠字号、字重与间距而非装饰建立层级，整体极度克制、几乎无阴影与描边，使界面在暗色环境中依然冷静、耐看。

# Color
- 主背景：#0A0F1E
- 次背景 / 卡片：#131A2E
- 主文字：#F8FAFC
- 次文字：#94A3B8
- 边界：#1E2844（1px）
- 主信号色：#00D4FF（霓虹蓝，用于高亮、发光、按钮、边框）
- 辅助信号色：#FF9F43（琥珀橙，用于规划/待定状态）
- 成功/交付色：#10B981
- 发光效果：#00D4FF 0 0 12px rgba(0,212,255,0.45)

# Font
- Heading & Body: Glow Sans SC (url: https://resource-static.cdn.bcebos.com/fonts/GlowSansSC-Normal-Regular.woff2)
# Animation
## 元素动画
- 动画极简且线性。元素沿着网格线滑入到位；
## 入场动画
- 没有弹跳或弹性效果，页面滚动像文档一样自然，有缓动效果（ease-out）；
## 过渡动画
- 内容加载时采用淡入或轻微位移；
## 动画实现
- 项目中集成了 tailwindcss-intersect 插件，可以使用类似下述的方式来实现元素进入视口时的动画效果：
opacity-0 intersect:opacity-100 transition duration-700
- 同时可使用 motion/react 配合实现动画。

# Layout
- 内容被组织在清晰的模块中。大量留白用于区分不同区块，
- 偏好左对齐文本和结构化的图像排布，不做装饰性错位。

# Elements
- 偏好使用极简线性图表，统一笔画粗细，无填充
- 阴影 ≈ 0，边框 ≤ 1px，弱化按钮感，主按钮 ≠ 大色块，更多强调文字