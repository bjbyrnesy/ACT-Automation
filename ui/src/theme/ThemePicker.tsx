import { useTheme } from "./ThemeProvider";
import type { ThemeId } from "./themes";
import "./ThemePicker.css";

type Props = {
  compact?: boolean;
};

export function ThemePicker({ compact = false }: Props) {
  const { themeId, setThemeId, themes } = useTheme();

  if (compact) {
    return (
      <label className="theme-picker theme-picker--compact">
        <span className="theme-picker__sr">Theme</span>
        <select
          aria-label="Theme"
          value={themeId}
          onChange={(event) => setThemeId(event.target.value as ThemeId)}
        >
          {themes.map((theme) => (
            <option key={theme.id} value={theme.id}>
              {theme.label}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <fieldset className="theme-picker">
      <legend>Theme</legend>
      <div className="theme-picker__grid" role="list">
        {themes.map((theme) => {
          const selected = theme.id === themeId;
          return (
            <button
              key={theme.id}
              type="button"
              role="listitem"
              className={
                selected
                  ? "theme-picker__swatch theme-picker__swatch--active"
                  : "theme-picker__swatch"
              }
              onClick={() => setThemeId(theme.id)}
              aria-pressed={selected}
            >
              <span
                className="theme-picker__preview"
                style={{
                  background: `linear-gradient(135deg, ${theme.colors.bg} 0 45%, ${theme.colors.bgPanel} 45% 75%, ${theme.colors.accent} 75% 100%)`,
                  borderColor: theme.colors.border,
                }}
                aria-hidden="true"
              />
              <span className="theme-picker__meta">
                <strong>{theme.label}</strong>
                <span>{theme.description}</span>
              </span>
            </button>
          );
        })}
      </div>
    </fieldset>
  );
}
