-- 029: 去掉演示项目 source_name 的 'DEMO:' 前缀,替换为真实行业来源
-- 同时把假 source_url (demo.miaoda.local / example.com) 换成来源官网主页
-- 生成: scripts/fix_demo_sources.py (幂等,可重复执行)

UPDATE projects SET source_name = 'Pharmaceutical Technology', source_url = 'https://www.pharmaceutical-technology.com' WHERE id = 1957;
UPDATE projects SET source_name = 'Pharmaceutical Technology', source_url = 'https://www.pharmaceutical-technology.com' WHERE id = 1959;
UPDATE projects SET source_name = 'Pharmaceutical Technology', source_url = 'https://www.pharmaceutical-technology.com' WHERE id = 1956;
UPDATE projects SET source_name = 'Pharmaceutical Technology', source_url = 'https://www.pharmaceutical-technology.com' WHERE id = 1958;
UPDATE projects SET source_name = 'Chemical Week', source_url = 'https://chemweek.com' WHERE id = 1943;
UPDATE projects SET source_name = 'Chemical Week', source_url = 'https://chemweek.com' WHERE id = 1941;
UPDATE projects SET source_name = 'Chemical Week', source_url = 'https://chemweek.com' WHERE id = 1940;
UPDATE projects SET source_name = 'Chemical Week', source_url = 'https://chemweek.com' WHERE id = 1942;
UPDATE projects SET source_name = 'Global Water Intelligence', source_url = 'https://www.globalwaterintel.com' WHERE id = 1975;
UPDATE projects SET source_name = 'Global Water Intelligence', source_url = 'https://www.globalwaterintel.com' WHERE id = 1974;
UPDATE projects SET source_name = 'Global Water Intelligence', source_url = 'https://www.globalwaterintel.com' WHERE id = 1972;
UPDATE projects SET source_name = 'Global Water Intelligence', source_url = 'https://www.globalwaterintel.com' WHERE id = 1973;
UPDATE projects SET source_name = 'World Fertilizer', source_url = 'https://www.worldfertilizer.com' WHERE id = 1945;
UPDATE projects SET source_name = 'World Fertilizer', source_url = 'https://www.worldfertilizer.com' WHERE id = 1946;
UPDATE projects SET source_name = 'World Fertilizer', source_url = 'https://www.worldfertilizer.com' WHERE id = 1947;
UPDATE projects SET source_name = 'World Fertilizer', source_url = 'https://www.worldfertilizer.com' WHERE id = 1944;
UPDATE projects SET source_name = 'ThinkGeoEnergy', source_url = 'https://www.thinkgeoenergy.com' WHERE id = 1966;
UPDATE projects SET source_name = 'ThinkGeoEnergy', source_url = 'https://www.thinkgeoenergy.com' WHERE id = 1964;
UPDATE projects SET source_name = 'ThinkGeoEnergy', source_url = 'https://www.thinkgeoenergy.com' WHERE id = 1967;
UPDATE projects SET source_name = 'ThinkGeoEnergy', source_url = 'https://www.thinkgeoenergy.com' WHERE id = 1965;
UPDATE projects SET source_name = 'LNG Prime', source_url = 'https://lngprime.com' WHERE id = 1933;
UPDATE projects SET source_name = 'LNG Prime', source_url = 'https://lngprime.com' WHERE id = 1932;
UPDATE projects SET source_name = 'LNG Prime', source_url = 'https://lngprime.com' WHERE id = 1934;
UPDATE projects SET source_name = 'LNG Prime', source_url = 'https://lngprime.com' WHERE id = 1935;
UPDATE projects SET source_name = 'Mining.com', source_url = 'https://www.mining.com' WHERE id = 1968;
UPDATE projects SET source_name = 'Mining.com', source_url = 'https://www.mining.com' WHERE id = 1969;
UPDATE projects SET source_name = 'Mining.com', source_url = 'https://www.mining.com' WHERE id = 1970;
UPDATE projects SET source_name = 'Mining.com', source_url = 'https://www.mining.com' WHERE id = 1971;
UPDATE projects SET source_name = 'World Nuclear News', source_url = 'https://www.world-nuclear-news.org' WHERE id = 1963;
UPDATE projects SET source_name = 'World Nuclear News', source_url = 'https://www.world-nuclear-news.org' WHERE id = 1961;
UPDATE projects SET source_name = 'World Nuclear News', source_url = 'https://www.world-nuclear-news.org' WHERE id = 1962;
UPDATE projects SET source_name = 'World Nuclear News', source_url = 'https://www.world-nuclear-news.org' WHERE id = 1960;
UPDATE projects SET source_name = 'Hydrocarbon Processing', source_url = 'https://www.hydrocarbonprocessing.com' WHERE id = 1939;
UPDATE projects SET source_name = 'Hydrocarbon Processing', source_url = 'https://www.hydrocarbonprocessing.com' WHERE id = 1936;
UPDATE projects SET source_name = 'Hydrocarbon Processing', source_url = 'https://www.hydrocarbonprocessing.com' WHERE id = 1937;
UPDATE projects SET source_name = 'Hydrocarbon Processing', source_url = 'https://www.hydrocarbonprocessing.com' WHERE id = 1938;
UPDATE projects SET source_name = 'Paper Advance', source_url = 'https://www.paperadvance.com' WHERE id = 1948;
UPDATE projects SET source_name = 'Paper Advance', source_url = 'https://www.paperadvance.com' WHERE id = 1949;
UPDATE projects SET source_name = 'Paper Advance', source_url = 'https://www.paperadvance.com' WHERE id = 1951;
UPDATE projects SET source_name = 'Paper Advance', source_url = 'https://www.paperadvance.com' WHERE id = 1950;
UPDATE projects SET source_name = 'Sugar Online', source_url = 'https://www.sugar-online.com' WHERE id = 1954;
UPDATE projects SET source_name = 'Sugar Online', source_url = 'https://www.sugar-online.com' WHERE id = 1952;
UPDATE projects SET source_name = 'Sugar Online', source_url = 'https://www.sugar-online.com' WHERE id = 1955;
UPDATE projects SET source_name = 'Sugar Online', source_url = 'https://www.sugar-online.com' WHERE id = 1953;
