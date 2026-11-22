import {
  createContext,
  createElement,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  applyTheme,
  DEFAULT_THEME_ID,
  persistTheme,
  readStoredThemeId,
  THEMES,
  type ThemeId,
} from "./themes";

type ThemeContextValue = {
  themeId: ThemeId;
  setThemeId: (id: ThemeId) => void;
  themes: typeof THEMES;
};

const ThemeContext = createContext<ThemeContextValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [themeId, setThemeIdState] = useState<ThemeId>(() => {
    if (typeof window === "undefined") return DEFAULT_THEME_ID;
    return readStoredThemeId();
  });

  useEffect(() => {
    applyTheme(themeId);
  }, [themeId]);

  const value = useMemo<ThemeContextValue>(
    () => ({
      themeId,
      setThemeId: (id) => {
        setThemeIdState(id);
        persistTheme(id);
      },
      themes: THEMES,
    }),
    [themeId],
  );

  return createElement(ThemeContext.Provider, { value }, children);
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useTheme requires ThemeProvider");
  }
  return ctx;
}
