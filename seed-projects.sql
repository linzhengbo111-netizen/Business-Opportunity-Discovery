-- Seed script for Supabase `projects` table
-- Run this in Supabase Dashboard → SQL Editor to populate the projects table.
-- After running, the Dashboard will automatically switch from fallback data to live Supabase data.

INSERT INTO projects (name, country, flag, status, summary, source_name, source_url, source_date, stainless_steel, application)
VALUES
  ('FPSO Maria Quitéria', 'Brazil', '🇧🇷', 'Under Construction', 'Petrobras pre-salt Santos Basin', 'Petrobras', 'https://example.com', '2026-07-17', '', ''),
  ('FPSO Prosperity', 'Guyana', '🇬🇾', 'Delivered', 'ExxonMobil Stabroek block Payara', 'SBM Offshore', 'https://example.com', '2026-07-17', '', ''),
  ('FPSO Agogo', 'Angola', '🇦🇴', 'Under Construction', 'MODEC EPC contract for TotalEnergies', 'MODEC', 'https://example.com', '2026-07-17', '', ''),
  ('FPSO Zafiro', 'Nigeria', '🇳🇬', 'Planned', 'Replacement for aging FPSO', 'World Oil', 'https://example.com', '2026-07-17', '', ''),
  ('FPSO Rosebank', 'UK', '🇬🇧', 'Planned', 'Equinor''s major North Sea development project featuring advanced subsea production systems and stainless steel topside modules', 'Offshore Energy', 'https://example.com', '2026-07-17', '', ''),
  ('FPSO Atlanta', 'Brazil', '🇧🇷', 'Under Construction', 'Enauta''s Santos Basin project', 'Offshore Magazine', 'https://example.com', '2026-07-17', '', ''),
  ('FPSO Baobab', 'Côte d''Ivoire', '🇨🇮', 'Planned', 'FEED phase targeting 2028 startup', 'Offshore Energy', 'https://example.com', '2026-07-17', '', '');
