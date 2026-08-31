# 链接质量报告 (Link Quality Report)

> 生成时间: 2026-08-31 06:05 UTC
> 数据: Supabase `projects` + `candidate_events`

## projects (1213 rows)

| 状态 | 数量 |
|---|---|
| ✅ 有效文章/页面链接 | 54 |
| 📄 数据文件 (CSV/PDF/DOC 下载) | 48 |
| ⬜ 待补充 (无链接) | 1111 |
| ⚠️ 仍为泛页面 | 0 |

### 域名分布 (top 15)

| 域名 | 数量 |
|---|---|
| gov.br | 42 |
| offshore-energy.biz | 25 |
| splash247.com | 20 |
| nstauthority.co.uk | 11 |
| agencia.petrobras.com.br | 1 |
| oedigital.com | 1 |
| equinor.com | 1 |
| modec.com | 1 |

## candidate_events (2797 rows)

| 状态 | 数量 |
|---|---|
| ✅ 有效文章/页面链接 | 203 |
| 📄 数据文件 (CSV/PDF/DOC 下载) | 61 |
| ⬜ 待补充 (无链接) | 2533 |
| ⚠️ 仍为泛页面 | 0 |

### 域名分布 (top 15)

| 域名 | 数量 |
|---|---|
| offshore-energy.biz | 132 |
| gov.br | 52 |
| splash247.com | 50 |
| nstauthority.co.uk | 11 |
| sbmoffshore.com | 9 |
| modec.com | 2 |
| marketscreener.com | 1 |
| post.tokyoipo.com | 1 |
| oilfieldtechnology.com | 1 |
| oedigital.com | 1 |
| worldoil.com | 1 |
| agencia.petrobras.com.br | 1 |
| petroleum.gov.gy | 1 |
| equinor.com | 1 |

## 修复记录

- 3 个置顶 FPSO 项目已替换为官方/媒体报道文章:
  - FPSO ALMIRANTE TAMANDARE → agencia.petrobras.com.br (Petrobras 官方新闻)
  - FPSO BACALHAU → modec.com 新闻稿
  - FPSO SEPETIBA → oedigital.com 新闻
- Rosebank 项目 → equinor.com/energy/rosebank
- 指向首页/列表页/搜索页/下载目录页的链接已清空标记为 待补充
  (nstauthority field themes、epaguyana download-category、gov.br planos 列表、
   11 个行业垂直站首页、petroleum.gov.gy 首页、供应商门户等)
- 数据文件类链接 (ANP CSV 下载、NSTA 模板文件) 保留 — 可下载但非文章原文

## 建议后续

- 对 待补充 的行业垂直站项目 (hydrocarbonprocessing/lngprime/chemweek 等 11 站):
  crawler 抓取时未保存文章 URL，需重跑对应 adapter 并保留原文链接
- 对 nstauthority/epaguyana 数据类项目: 可在 AI 分析阶段提取具体文件直链
  (download-category 页面内有文件列表)
- 回滚数据: crawler/scripts/link_fix_backup.json (每次变更的 old/new URL)
