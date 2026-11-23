/** Built-in UI themes. Colors are applied as CSS variables on ``document.documentElement``. */

export type ThemeId =
  | "slate"
  | "midnight"
  | "zinc"
  | "navy"
  | "ember"
  | "dracula"
  | "paper"
  | "stone"
  | "high-contrast";

export type ThemeColors = {
  bg: string;
  bgPanel: string;
  bgElevated: string;
  bgInput: string;
  bgSubtle: string;
  border: string;
  borderStrong: string;
  text: string;
  textMuted: string;
  accent: string;
  accentHover: string;
  accentMuted: string;
  accentText: string;
  badge: string;
  badgeText: string;
  danger: string;
  dangerBorder: string;
  dangerBg: string;
  ok: string;
  diagramBg: string;
  colorScheme: "light" | "dark";
};

export type ThemeDefinition = {
  id: ThemeId;
  label: string;
  description: string;
  colors: ThemeColors;
};

export const THEMES: ThemeDefinition[] = [
  {
    id: "slate",
    label: "Slate",
    description: "Soft dark gray, neutral accent",
    colors: {
      bg: "#1a1d23",
      bgPanel: "#23262e",
      bgElevated: "#2b2f38",
      bgInput: "#16181e",
      bgSubtle: "#1e2229",
      border: "#3a3f4a",
      borderStrong: "#525866",
      text: "#eceef2",
      textMuted: "#9aa1ad",
      accent: "#e8eaed",
      accentHover: "#ffffff",
      accentMuted: "#343943",
      accentText: "#16181e",
      badge: "#323743",
      badgeText: "#c4c9d2",
      danger: "#f0a8a8",
      dangerBorder: "#6b3a3a",
      dangerBg: "#3a2222",
      ok: "#c4c9d2",
      diagramBg: "#14161b",
      colorScheme: "dark",
    },
  },
  {
    id: "midnight",
    label: "Midnight",
    description: "Deep charcoal, quiet UI",
    colors: {
      bg: "#0d0f12",
      bgPanel: "#15181d",
      bgElevated: "#1c2026",
      bgInput: "#0a0c0f",
      bgSubtle: "#12151a",
      border: "#2a2f38",
      borderStrong: "#3d4450",
      text: "#e6e8ec",
      textMuted: "#8b929e",
      accent: "#d7dbe2",
      accentHover: "#ffffff",
      accentMuted: "#2a303a",
      accentText: "#0d0f12",
      badge: "#22272f",
      badgeText: "#b8bec8",
      danger: "#f0a8a8",
      dangerBorder: "#5c3333",
      dangerBg: "#2a1818",
      ok: "#b8bec8",
      diagramBg: "#090b0e",
      colorScheme: "dark",
    },
  },
  {
    id: "zinc",
    label: "Zinc",
    description: "Cool gray dark",
    colors: {
      bg: "#18181b",
      bgPanel: "#222226",
      bgElevated: "#2a2a2f",
      bgInput: "#121215",
      bgSubtle: "#1c1c20",
      border: "#3f3f46",
      borderStrong: "#52525b",
      text: "#f4f4f5",
      textMuted: "#a1a1aa",
      accent: "#fafafa",
      accentHover: "#ffffff",
      accentMuted: "#3f3f46",
      accentText: "#18181b",
      badge: "#3f3f46",
      badgeText: "#d4d4d8",
      danger: "#fca5a5",
      dangerBorder: "#7f1d1d",
      dangerBg: "#2a1515",
      ok: "#d4d4d8",
      diagramBg: "#111113",
      colorScheme: "dark",
    },
  },
  {
    id: "navy",
    label: "Navy",
    description: "Dark blue-gray, blue accent",
    colors: {
      bg: "#121826",
      bgPanel: "#1a2233",
      bgElevated: "#222c40",
      bgInput: "#0e1420",
      bgSubtle: "#161e2e",
      border: "#2e3a52",
      borderStrong: "#445475",
      text: "#e8edf7",
      textMuted: "#9aa8c2",
      accent: "#3b82f6",
      accentHover: "#60a5fa",
      accentMuted: "#1e3a5f",
      accentText: "#ffffff",
      badge: "#243247",
      badgeText: "#b4c4e0",
      danger: "#f0a8a8",
      dangerBorder: "#6b3a3a",
      dangerBg: "#3a2222",
      ok: "#b4c4e0",
      diagramBg: "#0d121c",
      colorScheme: "dark",
    },
  },
  {
    id: "ember",
    label: "Ember",
    description: "Dark base, warm amber accent",
    colors: {
      bg: "#171412",
      bgPanel: "#211d1a",
      bgElevated: "#2a251f",
      bgInput: "#120f0d",
      bgSubtle: "#1c1815",
      border: "#3d342c",
      borderStrong: "#5a4c40",
      text: "#f3eee8",
      textMuted: "#b0a194",
      accent: "#e8a35c",
      accentHover: "#f0b574",
      accentMuted: "#3d2e1f",
      accentText: "#1a120a",
      badge: "#332b24",
      badgeText: "#d4c4b4",
      danger: "#f0a8a8",
      dangerBorder: "#6b3a3a",
      dangerBg: "#3a2222",
      ok: "#d4c4b4",
      diagramBg: "#100e0c",
      colorScheme: "dark",
    },
  },
  {
    id: "dracula",
    label: "Dracula",
    description: "Classic Dracula palette",
    colors: {
      // https://draculatheme.com/contribute (Background / Foreground / Purple / …)
      bg: "#282a36",
      bgPanel: "#21222c",
      bgElevated: "#343746",
      bgInput: "#191a21",
      bgSubtle: "#2b2d3a",
      border: "#44475a",
      borderStrong: "#6272a4",
      text: "#f8f8f2",
      textMuted: "#6272a4",
      accent: "#bd93f9",
      accentHover: "#d6b4ff",
      accentMuted: "#3b3355",
      accentText: "#282a36",
      badge: "#44475a",
      badgeText: "#f8f8f2",
      danger: "#ff5555",
      dangerBorder: "#ff5555",
      dangerBg: "#3a1f24",
      ok: "#50fa7b",
      diagramBg: "#21222c",
      colorScheme: "dark",
    },
  },
  {
    id: "paper",
    label: "Paper",
    description: "Soft gray light (not pure white)",
    colors: {
      bg: "#e8eaee",
      bgPanel: "#f3f4f6",
      bgElevated: "#ffffff",
      bgInput: "#ffffff",
      bgSubtle: "#eceef2",
      border: "#cfd3db",
      borderStrong: "#b0b6c2",
      text: "#1a1d24",
      textMuted: "#5c6575",
      accent: "#111827",
      accentHover: "#000000",
      accentMuted: "#d5d9e0",
      accentText: "#ffffff",
      badge: "#dde1e8",
      badgeText: "#4b5563",
      danger: "#b42318",
      dangerBorder: "#f3c4c0",
      dangerBg: "#fef3f2",
      ok: "#374151",
      diagramBg: "#dde1e8",
      colorScheme: "light",
    },
  },
  {
    id: "stone",
    label: "Stone",
    description: "Warm light gray workspace",
    colors: {
      bg: "#e7e5e4",
      bgPanel: "#f5f5f4",
      bgElevated: "#fafaf9",
      bgInput: "#fafaf9",
      bgSubtle: "#ebe9e7",
      border: "#d6d3d1",
      borderStrong: "#a8a29e",
      text: "#1c1917",
      textMuted: "#57534e",
      accent: "#292524",
      accentHover: "#0c0a09",
      accentMuted: "#d6d3d1",
      accentText: "#fafaf9",
      badge: "#e7e5e4",
      badgeText: "#57534e",
      danger: "#b42318",
      dangerBorder: "#f3c4c0",
      dangerBg: "#fef3f2",
      ok: "#44403c",
      diagramBg: "#d6d3d1",
      colorScheme: "light",
    },
  },
  {
    id: "high-contrast",
    label: "High contrast",
    description: "Black / white, strong borders",
    colors: {
      bg: "#000000",
      bgPanel: "#0a0a0a",
      bgElevated: "#141414",
      bgInput: "#000000",
      bgSubtle: "#0f0f0f",
      border: "#ffffff",
      borderStrong: "#ffffff",
      text: "#ffffff",
      textMuted: "#d4d4d4",
      accent: "#ffffff",
      accentHover: "#e5e5e5",
      accentMuted: "#262626",
      accentText: "#000000",
      badge: "#262626",
      badgeText: "#ffffff",
      danger: "#ff6b6b",
      dangerBorder: "#ff6b6b",
      dangerBg: "#2a0000",
      ok: "#ffffff",
      diagramBg: "#000000",
      colorScheme: "dark",
    },
  },
];

export const DEFAULT_THEME_ID: ThemeId = "slate";
export const THEME_STORAGE_KEY = "acta.theme";

const THEME_BY_ID = Object.fromEntries(
  THEMES.map((theme) => [theme.id, theme]),
) as Record<ThemeId, ThemeDefinition>;

export function isThemeId(value: string): value is ThemeId {
  return value in THEME_BY_ID;
}

export function getTheme(id: ThemeId): ThemeDefinition {
  return THEME_BY_ID[id] ?? THEME_BY_ID[DEFAULT_THEME_ID];
}

export function readStoredThemeId(): ThemeId {
  try {
    const raw = localStorage.getItem(THEME_STORAGE_KEY);
    if (raw && isThemeId(raw)) return raw;
  } catch {
    /* ignore */
  }
  return DEFAULT_THEME_ID;
}

export function applyTheme(id: ThemeId): void {
  const theme = getTheme(id);
  const root = document.documentElement;
  const { colors } = theme;
  root.dataset.theme = theme.id;
  root.style.setProperty("--bg", colors.bg);
  root.style.setProperty("--bg-panel", colors.bgPanel);
  root.style.setProperty("--bg-elevated", colors.bgElevated);
  root.style.setProperty("--bg-input", colors.bgInput);
  root.style.setProperty("--bg-subtle", colors.bgSubtle);
  root.style.setProperty("--border", colors.border);
  root.style.setProperty("--border-strong", colors.borderStrong);
  root.style.setProperty("--text", colors.text);
  root.style.setProperty("--text-muted", colors.textMuted);
  root.style.setProperty("--accent", colors.accent);
  root.style.setProperty("--accent-hover", colors.accentHover);
  root.style.setProperty("--accent-muted", colors.accentMuted);
  root.style.setProperty("--accent-text", colors.accentText);
  root.style.setProperty("--badge", colors.badge);
  root.style.setProperty("--badge-text", colors.badgeText);
  root.style.setProperty("--danger", colors.danger);
  root.style.setProperty("--danger-border", colors.dangerBorder);
  root.style.setProperty("--danger-bg", colors.dangerBg);
  root.style.setProperty("--ok", colors.ok);
  root.style.setProperty("--diagram-bg", colors.diagramBg);
  root.style.colorScheme = colors.colorScheme;
}

export function persistTheme(id: ThemeId): void {
  applyTheme(id);
  try {
    localStorage.setItem(THEME_STORAGE_KEY, id);
  } catch {
    /* ignore */
  }
}
