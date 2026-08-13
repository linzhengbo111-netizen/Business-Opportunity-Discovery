/**
 * FPSO 项目别名映射系统
 *
 * 用于跨来源项目归一化（政府文件、行业新闻、监管数据等不同来源
 * 对同一项目使用不同名称）。
 *
 * 设计原则：
 * - Key: 规范项目 ID (kebab-case, 格式: {country-slug}-{project-slug})
 * - Value: 该项目的所有已知别名数组，按常用度降序排列。
 *   第一个元素是推荐的显示名称（Display Name）。
 * - 别名包括：政府文件中的官方名称、行业新闻中的常用名、FPSO 船名、
 *   开发阶段名称（如 "Liza Phase 1"）、简称等。
 *
 * 使用方式：
 *   import { normalizeProjectName, getDisplayName } from './project_aliases';
 *   const id = normalizeProjectName('Payara Dev Project');  // → 'guyana-payara'
 */

export interface ProjectAliasEntry {
  /** 推荐的显示名称（第一个别名） */
  displayName: string;
  /** 所有已知别名 */
  aliases: string[];
  /** 所属国家/地区 */
  country: string;
}

// ---- 项目别名注册表 ------------------------------------------------

export const PROJECT_ALIASES: Record<string, ProjectAliasEntry> = {

  // ===================================================================
  // 圭亚那 (Guyana) — Stabroek Block, ExxonMobil
  // ===================================================================

  'guyana-liza-1': {
    displayName: 'Liza Phase 1 (FPSO Liza Destiny)',
    country: 'Guyana',
    aliases: [
      'Liza Phase 1',
      'FPSO Liza Destiny',
      'Liza Destiny',
      'Liza 1',
      'Liza Phase 1 Development',
      'Liza Destiny FPSO',
    ],
  },
  'guyana-liza-2': {
    displayName: 'Liza Phase 2 (FPSO Liza Unity)',
    country: 'Guyana',
    aliases: [
      'Liza Phase 2',
      'FPSO Liza Unity',
      'Liza Unity',
      'Liza 2',
      'Liza Phase 2 Development',
      'Liza Unity FPSO',
    ],
  },
  'guyana-payara': {
    displayName: 'Payara (FPSO Prosperity)',
    country: 'Guyana',
    aliases: [
      'Payara',
      'FPSO Prosperity',
      'Prosperity FPSO',
      'Payara Development',
      'Payara Project',
      'Payara Dev Project',
      'Payara FPSO',
      'Payara Field',
      'Prosperity',
      'FPSO Payara',
      'Payara Phase',
    ],
  },
  'guyana-yellowtail': {
    displayName: 'Yellowtail (FPSO ONE GUYANA)',
    country: 'Guyana',
    aliases: [
      'Yellowtail',
      'FPSO ONE GUYANA',
      'FPSO One Guyana',
      'One Guyana',
      'ONE GUYANA',
      'Yellowtail Development',
      'Yellowtail Project',
      'Yellowtail FPSO',
      'Yellowtail Field',
    ],
  },
  'guyana-uaru': {
    displayName: 'Uaru (FPSO Errea Wittu)',
    country: 'Guyana',
    aliases: [
      'Uaru',
      'FPSO Errea Wittu',
      'Errea Wittu',
      'Uaru Development',
      'Uaru Project',
      'Uaru FPSO',
      'Uaru Field',
    ],
  },
  'guyana-whiptail': {
    displayName: 'Whiptail (FPSO Jaguar)',
    country: 'Guyana',
    aliases: [
      'Whiptail',
      'FPSO Jaguar',
      'Jaguar FPSO',
      'Whiptail Development',
      'Whiptail Project',
      'Whiptail FPSO',
      'Whiptail Field',
    ],
  },
  'guyana-hammerhead': {
    displayName: 'Hammerhead',
    country: 'Guyana',
    aliases: [
      'Hammerhead',
      'Hammerhead Development',
      'Hammerhead Project',
      'Hammerhead FPSO',
      'Hammerhead Field',
    ],
  },
  'guyana-longtail': {
    displayName: 'Longtail',
    country: 'Guyana',
    aliases: [
      'Longtail',
      'Longtail Development',
      'Longtail Project',
      'Longtail FPSO',
      'Longtail Field',
    ],
  },
  'guyana-gas-to-energy': {
    displayName: 'Gas to Energy (Guyana)',
    country: 'Guyana',
    aliases: [
      'Gas to Energy',
      'Guyana Gas to Energy',
      'Gas-to-Energy',
      'Guyana Gas-to-Energy',
      'Gas to Energy Project',
      'Gas to Energy Guyana',
      'GtE Guyana',
      'Wales Gas to Energy',
    ],
  },

  // ===================================================================
  // 巴西 (Brazil) — Santos Basin, Campos Basin, pre-salt
  // ===================================================================

  'brazil-maria-quiteria': {
    displayName: 'FPSO Maria Quitéria',
    country: 'Brazil',
    aliases: [
      'FPSO Maria Quitéria',
      'FPSO Maria Quiteria',
      'Maria Quitéria',
      'Maria Quiteria',
      'FPSO Maria Quitéria (Parque das Baleias)',
    ],
  },
  'brazil-almirante-tamandare': {
    displayName: 'FPSO Almirante Tamandaré (Búzios)',
    country: 'Brazil',
    aliases: [
      'FPSO Almirante Tamandaré',
      'FPSO ALMIRANTE TAMANDARE',
      'Almirante Tamandaré',
      'ALMIRANTE TAMANDARE',
      'Almirante Tamandare',
      'Búzios 8 FPSO',
      'Buzios 8 FPSO',
    ],
  },
  'brazil-bacalhau': {
    displayName: 'FPSO Bacalhau (Equinor)',
    country: 'Brazil',
    aliases: [
      'FPSO Bacalhau',
      'FPSO BACALHAU',
      'Bacalhau',
      'BACALHAU',
      'Bacalhau FPSO',
      'Equinor Bacalhau',
      'Bacalhau Field',
    ],
  },
  'brazil-peregrino': {
    displayName: 'FPSO Peregrino (Equinor)',
    country: 'Brazil',
    aliases: [
      'FPSO Peregrino',
      'FPSO PEREGRINO',
      'Peregrino',
      'PEREGRINO',
      'Peregrino FPSO',
      'Equinor Peregrino',
      'Peregrino Field',
    ],
  },
  'brazil-pioneiro-de-libra': {
    displayName: 'FPSO Pioneiro de Libra',
    country: 'Brazil',
    aliases: [
      'FPSO Pioneiro de Libra',
      'FPSO PIONEIRO DE LIBRA',
      'Pioneiro de Libra',
      'PIONEIRO DE LIBRA',
      'Libra Pilot FPSO',
      'FPSO Pioneiro',
    ],
  },
  'brazil-cidade-de-caraguatatuba': {
    displayName: 'FPSO Cidade de Caraguatatuba (MV-27)',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Caraguatatuba',
      'FPSO CIDADE DE CARAGUATATUBA',
      'Cidade de Caraguatatuba',
      'CIDADE DE CARAGUATATUBA',
      'MV-27',
      'FPSO CCG',
    ],
  },
  'brazil-frade': {
    displayName: 'FPSO Frade',
    country: 'Brazil',
    aliases: [
      'FPSO Frade',
      'FPSO FRADE',
      'Frade',
      'FRADE',
      'Frade FPSO',
      'Chevron Frade',
    ],
  },
  'brazil-sepetiba': {
    displayName: 'FPSO Cidade de Sepetiba (Sépia)',
    country: 'Brazil',
    aliases: [
      'FPSO Sepetiba',
      'FPSO SEPETIBA',
      'FPSO Cidade de Sepetiba',
      'Cidade de Sepetiba',
      'Sepetiba',
      'SEPETIBA',
      'Sépia FPSO',
      'Sepia FPSO',
    ],
  },
  'brazil-bravo': {
    displayName: 'FPSO Bravo (Petrobras)',
    country: 'Brazil',
    aliases: [
      'FPSO Bravo',
      'FPSO BRAVO',
      'Bravo FPSO',
      'BRAVO',
    ],
  },
  'brazil-carioca': {
    displayName: 'FPSO Carioca (Sépia Area)',
    country: 'Brazil',
    aliases: [
      'FPSO Carioca',
      'FPSO CARIOCA',
      'Carioca',
      'CARIOCA',
      'Carioca FPSO',
    ],
  },
  'brazil-forte': {
    displayName: 'FPSO Forte',
    country: 'Brazil',
    aliases: [
      'FPSO Forte',
      'FPSO FORTE',
      'Forte',
      'FORTE',
      'Forte FPSO',
    ],
  },
  'suriname-fpso': {
    displayName: 'Suriname FPSO (SBM Offshore)',
    country: 'Suriname',
    aliases: [
      'Suriname FPSO',
      'SBM Offshore Suriname FPSO',
      'Suriname-bound FPSO',
    ],
  },
  'brazil-atlanta': {
    displayName: 'FPSO Atlanta',
    country: 'Brazil',
    aliases: [
      'FPSO Atlanta',
      'Atlanta FPSO',
      'Atlanta',
      'Atlanta Field FPSO',
      'Enauta Atlanta',
    ],
  },
  'brazil-alexandre-de-gusmao': {
    displayName: 'FPSO Alexandre de Gusmão',
    country: 'Brazil',
    aliases: [
      'FPSO Alexandre de Gusmão',
      'FPSO ALEXANDRE DE GUSMÃO',
      'Alexandre de Gusmão',
      'Alexandre de Gusmao',
      'ALEXANDRE DE GUSMÃO',
      'FPSO Alexandre de Gusmao',
    ],
  },
  'brazil-almirante-barroso': {
    displayName: 'FPSO Almirante Barroso',
    country: 'Brazil',
    aliases: [
      'FPSO Almirante Barroso',
      'FPSO ALMIRANTE BARROSO',
      'Almirante Barroso',
      'ALMIRANTE BARROSO',
    ],
  },
  'brazil-duque-de-caxias': {
    displayName: 'FPSO Duque de Caxias',
    country: 'Brazil',
    aliases: [
      'FPSO Duque de Caxias',
      'FPSO Marechal Duque de Caxias',
      'Duque de Caxias',
      'Marechal Duque de Caxias',
    ],
  },
  'brazil-anita-garibaldi': {
    displayName: 'FPSO Anita Garibaldi',
    country: 'Brazil',
    aliases: [
      'FPSO Anita Garibaldi',
      'Anita Garibaldi',
    ],
  },
  'brazil-anna-nery': {
    displayName: 'FPSO Anna Nery',
    country: 'Brazil',
    aliases: [
      'FPSO Anna Nery',
      'Anna Nery',
    ],
  },
  'brazil-guanabara': {
    displayName: 'FPSO Guanabara',
    country: 'Brazil',
    aliases: [
      'FPSO Guanabara',
      'Guanabara FPSO',
      'Guanabara',
      'FPSO Guanabara (Mero)',
    ],
  },
  'brazil-buzios': {
    displayName: 'Búzios Field FPSOs',
    country: 'Brazil',
    aliases: [
      'Búzios',
      'Buzios',
      'Búzios Field',
      'Buzios Field',
      'FPSO Búzios',
      'FPSO Buzios',
    ],
  },
  'brazil-mero': {
    displayName: 'Mero Field FPSOs',
    country: 'Brazil',
    aliases: [
      'Mero',
      'Mero Field',
      'FPSO Mero',
      'Libra Block Mero',
      'Alexandre de Gusmão',
      'FPSO Alexandre de Gusmão',
    ],
  },
  'brazil-marlim': {
    displayName: 'FPSO Marlim',
    country: 'Brazil',
    aliases: [
      'FPSO Marlim',
      'FPSO Marlim Sul',
      'Marlim',
      'Marlim Sul',
    ],
  },
  'brazil-cidade-de-angra-dos-reis': {
    displayName: 'FPSO Cidade de Angra dos Reis',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Angra dos Reis',
      'Cidade de Angra dos Reis',
    ],
  },
  'brazil-cidade-de-ilhabela': {
    displayName: 'FPSO Cidade de Ilhabela',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Ilhabela',
      'Cidade de Ilhabela',
    ],
  },
  'brazil-cidade-de-itaguai': {
    displayName: 'FPSO Cidade de Itaguaí',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Itaguaí',
      'FPSO Cidade de Itaguai',
      'Cidade de Itaguaí',
      'Cidade de Itaguai',
    ],
  },
  'brazil-cidade-de-marica': {
    displayName: 'FPSO Cidade de Maricá',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Maricá',
      'FPSO Cidade de Marica',
      'Cidade de Maricá',
      'Cidade de Marica',
    ],
  },
  'brazil-cidade-de-saquarema': {
    displayName: 'FPSO Cidade de Saquarema',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Saquarema',
      'Cidade de Saquarema',
    ],
  },
  'brazil-cidade-de-santos': {
    displayName: 'FPSO Cidade de Santos',
    country: 'Brazil',
    aliases: [
      'FPSO Cidade de Santos',
      'Cidade de Santos',
    ],
  },
  'brazil-tartaruga-verde': {
    displayName: 'Tartaruga Verde (FPSO Tartaruga Verde)',
    country: 'Brazil',
    aliases: [
      'Tartaruga Verde',
      'FPSO Tartaruga Verde',
      'Tartaruga Verde FPSO',
      'Tartaruga Verde Field',
    ],
  },
  'brazil-espirito-santo': {
    displayName: 'FPSO Espirito Santo',
    country: 'Brazil',
    aliases: [
      'FPSO Espirito Santo',
      'FPSO Espírito Santo',
      'Espirito Santo FPSO',
    ],
  },
  'brazil-p-74': {
    displayName: 'FPSO P-74',
    country: 'Brazil',
    aliases: [
      'FPSO P-74',
      'P-74 FPSO',
      'P-74',
      'PETROBRAS 74',
      'Petrobras 74',
    ],
  },
  'brazil-p-75': {
    displayName: 'FPSO P-75',
    country: 'Brazil',
    aliases: [
      'FPSO P-75',
      'P-75 FPSO',
      'P-75',
      'PETROBRAS 75',
      'Petrobras 75',
    ],
  },
  'brazil-p-76': {
    displayName: 'FPSO P-76',
    country: 'Brazil',
    aliases: [
      'FPSO P-76',
      'P-76 FPSO',
      'P-76',
      'PETROBRAS 76',
      'Petrobras 76',
    ],
  },
  'brazil-p-77': {
    displayName: 'FPSO P-77',
    country: 'Brazil',
    aliases: [
      'FPSO P-77',
      'P-77 FPSO',
      'P-77',
      'PETROBRAS 77',
      'Petrobras 77',
    ],
  },
  'brazil-p-78': {
    displayName: 'FPSO P-78',
    country: 'Brazil',
    aliases: [
      'FPSO P-78',
      'P-78 FPSO',
      'P-78',
      'PETROBRAS 78',
      'Petrobras 78',
    ],
  },
  'brazil-p-79': {
    displayName: 'FPSO P-79',
    country: 'Brazil',
    aliases: [
      'FPSO P-79',
      'P-79 FPSO',
      'P-79',
      'PETROBRAS 79',
      'Petrobras 79',
    ],
  },
  'brazil-p-80': {
    displayName: 'FPSO P-80',
    country: 'Brazil',
    aliases: [
      'FPSO P-80',
      'P-80 FPSO',
      'P-80',
    ],
  },
  'brazil-p-81': {
    displayName: 'FPSO P-81',
    country: 'Brazil',
    aliases: [
      'FPSO P-81',
      'P-81 FPSO',
      'P-81',
    ],
  },
  'brazil-p-82': {
    displayName: 'FPSO P-82',
    country: 'Brazil',
    aliases: [
      'FPSO P-82',
      'P-82 FPSO',
      'P-82',
    ],
  },
  'brazil-p-83': {
    displayName: 'FPSO P-83',
    country: 'Brazil',
    aliases: [
      'FPSO P-83',
      'P-83 FPSO',
      'P-83',
    ],
  },
  'brazil-p-84': {
    displayName: 'FPSO P-84',
    country: 'Brazil',
    aliases: [
      'FPSO P-84',
      'P-84 FPSO',
      'P-84',
    ],
  },
  'brazil-p-85': {
    displayName: 'FPSO P-85',
    country: 'Brazil',
    aliases: [
      'FPSO P-85',
      'P-85 FPSO',
      'P-85',
    ],
  },

  // ===================================================================
  // 英国 (UK) — North Sea
  // ===================================================================

  'uk-rosebank': {
    displayName: 'Rosebank (FPSO Rosebank)',
    country: 'UK',
    aliases: [
      'Rosebank',
      'FPSO Rosebank',
      'Rosebank FPSO',
      'Rosebank Development',
      'Rosebank Project',
      'Rosebank Field',
      'Equinor Rosebank',
      'Rosebank Oil Field',
      'Rosebank North Sea',
    ],
  },
  'uk-cambo': {
    displayName: 'Cambo',
    country: 'UK',
    aliases: [
      'Cambo',
      'Cambo Field',
      'Cambo Development',
      'Cambo Project',
      'Cambo FPSO',
    ],
  },
  'uk-clair': {
    displayName: 'Clair Field',
    country: 'UK',
    aliases: [
      'Clair',
      'Clair Field',
      'Clair Ridge',
      'Clair Development',
    ],
  },
  'uk-schiehallion': {
    displayName: 'Schiehallion (FPSO Glen Lyon)',
    country: 'UK',
    aliases: [
      'Schiehallion',
      'FPSO Glen Lyon',
      'Glen Lyon FPSO',
      'Glen Lyon',
      'Schiehallion Field',
      'Schiehallion FPSO',
    ],
  },
  'uk-foinaven': {
    displayName: 'Foinaven',
    country: 'UK',
    aliases: [
      'Foinaven',
      'FPSO Foinaven',
      'FPSO Petrojarl Foinaven',
      'Foinaven Field',
      'Foinaven FPSO',
    ],
  },
  'uk-captain': {
    displayName: 'Captain Field (FPSO Captain)',
    country: 'UK',
    aliases: [
      'Captain',
      'FPSO Captain',
      'Captain Field',
      'Captain FPSO',
    ],
  },
  'uk-mariner': {
    displayName: 'Mariner Field',
    country: 'UK',
    aliases: [
      'Mariner',
      'Mariner Field',
      'Mariner FPSO',
      'Equinor Mariner',
    ],
  },
  'uk-buzzard': {
    displayName: 'Buzzard Field',
    country: 'UK',
    aliases: [
      'Buzzard',
      'Buzzard Field',
      'Buzzard FPSO',
    ],
  },
  'uk-victory': {
    displayName: 'Victory',
    country: 'UK',
    aliases: [
      'Victory',
      'Victory Field',
      'Victory Development',
      'Victory Project',
      'Victory FPSO',
      'Victory Gas Field',
    ],
  },
  'uk-belinda': {
    displayName: 'Belinda',
    country: 'UK',
    aliases: [
      'Belinda',
      'Belinda Field',
      'Belinda Development',
      'Belinda Project',
      'Belinda FPSO',
    ],
  },
  'uk-triton': {
    displayName: 'Triton FPSO',
    country: 'UK',
    aliases: [
      'FPSO Triton',
      'Triton FPSO',
      'Triton',
      'Triton Area',
    ],
  },

  // ===================================================================
  // 安哥拉 (Angola)
  // ===================================================================

  'angola-agogo': {
    displayName: 'FPSO Agogo',
    country: 'Angola',
    aliases: [
      'FPSO Agogo',
      'Agogo FPSO',
      'Agogo',
      'Agogo Field',
      'Agogo Development',
      'Agogo Project',
      'Agogo FFD',
      'MODEC Agogo',
    ],
  },
  'angola-greater-plutonio': {
    displayName: 'FPSO Greater Plutonio',
    country: 'Angola',
    aliases: [
      'FPSO Greater Plutonio',
      'Greater Plutonio',
      'FPSO Plutonio',
      'Plutonio FPSO',
    ],
  },
  'angola-kizomba-a': {
    displayName: 'FPSO Kizomba A',
    country: 'Angola',
    aliases: [
      'FPSO Kizomba A',
      'Kizomba A',
      'Kizomba A FPSO',
    ],
  },
  'angola-kaombo': {
    displayName: 'Kaombo (FPSO Kaombo Norte / Sul)',
    country: 'Angola',
    aliases: [
      'Kaombo',
      'FPSO Kaombo Norte',
      'FPSO Kaombo Sul',
      'Kaombo Norte',
      'Kaombo Sul',
      'Kaombo Project',
    ],
  },
  'angola-dalia': {
    displayName: 'FPSO Dalia',
    country: 'Angola',
    aliases: [
      'FPSO Dalia',
      'Dalia FPSO',
      'Dalia',
      'Dalia Field',
    ],
  },
  'angola-girassol': {
    displayName: 'FPSO Girassol',
    country: 'Angola',
    aliases: [
      'FPSO Girassol',
      'Girassol FPSO',
      'Girassol',
      'Girassol Field',
    ],
  },
  'angola-pazflor': {
    displayName: 'FPSO Pazflor',
    country: 'Angola',
    aliases: [
      'FPSO Pazflor',
      'Pazflor FPSO',
      'Pazflor',
    ],
  },
  'angola-clov': {
    displayName: 'FPSO CLOV',
    country: 'Angola',
    aliases: [
      'FPSO CLOV',
      'CLOV FPSO',
      'CLOV',
      'CLOV Field',
    ],
  },
  'angola-ndungu': {
    displayName: 'FPSO Ndungu',
    country: 'Angola',
    aliases: [
      'FPSO Ndungu',
      'Ndungu FPSO',
      'Ndungu',
      'Ndungu Field',
    ],
  },

  // ===================================================================
  // 尼日利亚 (Nigeria)
  // ===================================================================

  'nigeria-zafiro': {
    displayName: 'FPSO Zafiro',
    country: 'Nigeria',
    aliases: [
      'FPSO Zafiro',
      'Zafiro FPSO',
      'Zafiro',
      'Zafiro Field',
      'Zafiro Development',
      'Zafiro Project',
      'Nigeria Zafiro',
    ],
  },
  'nigeria-bonga': {
    displayName: 'FPSO Bonga',
    country: 'Nigeria',
    aliases: [
      'FPSO Bonga',
      'Bonga FPSO',
      'Bonga',
      'Bonga Field',
      'Bonga Main',
      'Bonga North',
      'Bonga South West',
      'FPSO Bonga North',
      'FPSO Bonga South West',
    ],
  },
  'nigeria-egina': {
    displayName: 'FPSO Egina',
    country: 'Nigeria',
    aliases: [
      'FPSO Egina',
      'Egina FPSO',
      'Egina',
      'Egina Field',
    ],
  },
  'nigeria-akpo': {
    displayName: 'FPSO Akpo',
    country: 'Nigeria',
    aliases: [
      'FPSO Akpo',
      'Akpo FPSO',
      'Akpo',
      'Akpo Field',
    ],
  },
  'nigeria-erha': {
    displayName: 'FPSO Erha',
    country: 'Nigeria',
    aliases: [
      'FPSO Erha',
      'Erha FPSO',
      'Erha',
      'Erha Field',
    ],
  },
  'nigeria-agbami': {
    displayName: 'FPSO Agbami',
    country: 'Nigeria',
    aliases: [
      'FPSO Agbami',
      'Agbami FPSO',
      'Agbami',
      'Agbami Field',
    ],
  },
  'nigeria-usan': {
    displayName: 'FPSO Usan',
    country: 'Nigeria',
    aliases: [
      'FPSO Usan',
      'Usan FPSO',
      'Usan',
      'Usan Field',
    ],
  },

  // ===================================================================
  // 挪威 (Norway)
  // ===================================================================

  'norway-johan-castberg': {
    displayName: 'Johan Castberg (FPSO Johan Castberg)',
    country: 'Norway',
    aliases: [
      'Johan Castberg',
      'FPSO Johan Castberg',
      'Johan Castberg FPSO',
      'Johan Castberg Field',
      'Castberg',
    ],
  },

  // ===================================================================
  // 美国 (USA) — Gulf of Mexico
  // ===================================================================

  'usa-vito': {
    displayName: 'Vito (FPSO Vito)',
    country: 'USA',
    aliases: [
      'Vito',
      'FPSO Vito',
      'Vito FPSO',
      'Vito Field',
      'Shell Vito',
    ],
  },
  'usa-argos': {
    displayName: 'Argos (FPSO Argos)',
    country: 'USA',
    aliases: [
      'Argos',
      'FPSO Argos',
      'Argos FPSO',
      'Argos Platform',
      'Mad Dog 2',
      'Mad Dog Phase 2',
      'BP Argos',
    ],
  },
  'usa-stones': {
    displayName: 'Stones (FPSO Turritella)',
    country: 'USA',
    aliases: [
      'Stones',
      'FPSO Stones',
      'FPSO Turritella',
      'Turritella',
      'Stones Field',
      'Shell Stones',
    ],
  },
  'usa-who-dat': {
    displayName: 'Who Dat Field',
    country: 'USA',
    aliases: [
      'Who Dat',
      'Who Dat Field',
      'Who Dat FPSO',
    ],
  },
  'usa-salamanca': {
    displayName: 'Salamanca (FPSO Salamanca)',
    country: 'USA',
    aliases: [
      'Salamanca',
      'FPSO Salamanca',
      'Salamanca FPSO',
    ],
  },

  // ===================================================================
  // 加纳 (Ghana)
  // ===================================================================

  'ghana-jubilee': {
    displayName: 'Jubilee (FPSO Kwame Nkrumah)',
    country: 'Ghana',
    aliases: [
      'Jubilee',
      'FPSO Kwame Nkrumah',
      'Kwame Nkrumah',
      'Jubilee Field',
      'Jubilee FPSO',
    ],
  },
  'ghana-ten': {
    displayName: 'TEN (FPSO John Evans Atta Mills)',
    country: 'Ghana',
    aliases: [
      'TEN',
      'TEN Field',
      'FPSO John Evans Atta Mills',
      'John Evans Atta Mills',
      'TEN FPSO',
    ],
  },
  'ghana-pecan': {
    displayName: 'Pecan (FPSO John Agyekum Kufuor)',
    country: 'Ghana',
    aliases: [
      'Pecan',
      'Pecan Field',
      'FPSO John Agyekum Kufuor',
      'John Agyekum Kufuor',
      'Pecan FPSO',
      'JAK FPSO',
    ],
  },

  // ===================================================================
  // 科特迪瓦 (Ivory Coast / Côte d'Ivoire)
  // ===================================================================

  'ivory-coast-baleine': {
    displayName: 'Baleine (FPSO Baleine)',
    country: 'Ivory Coast',
    aliases: [
      'Baleine',
      'FPSO Baleine',
      'Baleine FPSO',
      'Baleine Field',
      'Baleine Phase',
      'Eni Baleine',
    ],
  },
  'ivory-coast-baobab': {
    displayName: 'Baobab',
    country: 'Ivory Coast',
    aliases: [
      'Baobab',
      'FPSO Baobab',
      'Baobab FPSO',
      'Baobab Field',
      'Baobab Development',
      'Baobab Project',
      'Baobab Phase',
    ],
  },

  // ===================================================================
  // 塞内加尔 (Senegal)
  // ===================================================================

  'senegal-sangomar': {
    displayName: 'Sangomar (FPSO Léopold Sédar Senghor)',
    country: 'Senegal',
    aliases: [
      'Sangomar',
      'Sangomar Field',
      'FPSO Léopold Sédar Senghor',
      'Leopold Sedar Senghor',
      'Léopold Sédar Senghor',
      'Sangomar FPSO',
      'Sangomar Development',
    ],
  },
};

// ---- 归一化函数 ----------------------------------------------------

/**
 * 将原始项目名归一化为规范项目 ID。
 *
 * 匹配策略（按优先级）：
 * 1. 精确匹配（忽略大小写和首尾空白）
 * 2. 去除 "FPSO " 前缀后再精确匹配
 * 3. 关键词匹配：提取 rawName 中的关键实词，与各项目别名集计算重合度
 *
 * @param rawName - 原始项目名（来自爬虫、新闻、政府文件等）
 * @returns 规范项目 ID，如果无法匹配则返回 null
 */
export function normalizeProjectName(rawName: string): string | null {
  if (!rawName || typeof rawName !== 'string') {
    return null;
  }

  const cleaned = rawName.trim();
  if (cleaned.length === 0) {
    return null;
  }

  const cleanedLower = cleaned.toLowerCase();

  // ---- Strategy 1: exact match against all aliases ----
  for (const [canonicalId, entry] of Object.entries(PROJECT_ALIASES)) {
    for (const alias of entry.aliases) {
      if (alias.toLowerCase() === cleanedLower) {
        return canonicalId;
      }
    }
  }

  // ---- Strategy 2: strip "FPSO " prefix and try again ----
  const stripped = cleanedLower.replace(/^fpso\s+/i, '').trim();
  if (stripped !== cleanedLower) {
    for (const [canonicalId, entry] of Object.entries(PROJECT_ALIASES)) {
      for (const alias of entry.aliases) {
        const aliasStripped = alias.toLowerCase().replace(/^fpso\s+/i, '').trim();
        if (aliasStripped === stripped) {
          return canonicalId;
        }
      }
    }
  }

  // ---- Strategy 3: keyword-based fuzzy matching ----
  // Tokenize the raw name into keywords, skipping generic words
  const genericWords = new Set([
    'fpso', 'the', 'a', 'an', 'for', 'and', 'with', 'new', 'first', 'latest',
    'project', 'vessel', 'unit', 'platform', 'production', 'storage',
    'offloading', 'of', 'in', 'at', 'to', 'is', 'on', 'as', 'by',
    'its', 'will', 'has', 'been', 'from', 'was', 'that', 'this',
    'next', 'two', 'three', 'four', 'one', 'major', 'another',
    'floating', 'be', 'it', 'or', 'second', 'third', 'phase',
    'field', 'development', 'dev',
  ]);

  const rawTokens = new Set(
    cleanedLower
      .split(/[\s\-–—/.,;:!?()"']+/)
      .filter(t => t.length >= 2 && !genericWords.has(t))
  );

  if (rawTokens.size === 0) {
    return null;
  }

  // Score each project by how many keywords match its aliases
  let bestMatch: { id: string; score: number } | null = null;

  for (const [canonicalId, entry] of Object.entries(PROJECT_ALIASES)) {
    const allAliasText = entry.aliases.join(' ').toLowerCase();
    const aliasTokens = new Set(
      allAliasText.split(/[\s\-–—/.,;:!?()"']+/).filter(t => t.length >= 2)
    );

    let score = 0;
    for (const token of rawTokens) {
      if (aliasTokens.has(token)) {
        score += 1;
      }
    }

    // Normalize score by rawTokens size (precision) and aliasTokens coverage (recall)
    const precision = rawTokens.size > 0 ? score / rawTokens.size : 0;
    const recall = aliasTokens.size > 0 ? score / Math.min(rawTokens.size, aliasTokens.size) : 0;

    // Only consider matches: score >= 2 for multi-token inputs,
    // or score == 1 with high precision for single-token inputs (e.g. "Stones FPSO")
    if (precision >= 0.5 && recall >= 0.4) {
      if (score >= 2 || (score === 1 && precision >= 0.8)) {
        const combinedScore = precision * 0.6 + recall * 0.4;
        if (!bestMatch || combinedScore > bestMatch.score) {
          bestMatch = { id: canonicalId, score: combinedScore };
        }
      }
    }
  }

  return bestMatch ? bestMatch.id : null;
}

/**
 * 获取项目的推荐显示名称。
 *
 * @param canonicalId - 规范项目 ID
 * @returns 显示名称，如果 ID 无效则返回原始 ID
 */
export function getDisplayName(canonicalId: string): string {
  const entry = PROJECT_ALIASES[canonicalId];
  return entry ? entry.displayName : canonicalId;
}

/**
 * 获取项目所属国家。
 *
 * @param canonicalId - 规范项目 ID
 * @returns 国家名称，如果 ID 无效则返回空字符串
 */
export function getProjectCountry(canonicalId: string): string {
  const entry = PROJECT_ALIASES[canonicalId];
  return entry ? entry.country : '';
}

/**
 * 获取项目的所有别名。
 *
 * @param canonicalId - 规范项目 ID
 * @returns 别名数组，如果 ID 无效则返回空数组
 */
export function getAliases(canonicalId: string): string[] {
  const entry = PROJECT_ALIASES[canonicalId];
  return entry ? [...entry.aliases] : [];
}

/**
 * 列出所有已知的规范项目 ID。
 */
export function getAllCanonicalIds(): string[] {
  return Object.keys(PROJECT_ALIASES);
}

/**
 * 根据国家过滤项目 ID。
 */
export function getProjectIdsByCountry(country: string): string[] {
  return Object.entries(PROJECT_ALIASES)
    .filter(([, entry]) => entry.country.toLowerCase() === country.toLowerCase())
    .map(([id]) => id);
}
