"use client";

import { createContext, useContext, useEffect, useState } from "react";

export type Theme = "light" | "dark";

interface ThemeCtx {
  theme: Theme;
  toggleTheme: () => void;
}

const STORAGE_KEY = "careops-theme";

const Context = createContext<ThemeCtx | null>(null);

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

function readInitialTheme(): Theme {
  // Guards SSR (no window) -- the real value is computed again on the
  // client's hydration pass, where window is genuinely available. Doesn't
  // risk a hydration mismatch: this state never drives ThemeProvider's own
  // JSX, only the DOM-mutation effect below (which runs post-hydration).
  if (typeof window === "undefined") return "light";
  const stored = window.localStorage.getItem(STORAGE_KEY) as Theme | null;
  return stored ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setTheme] = useState<Theme>(readInitialTheme);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  function toggleTheme() {
    setTheme((prev) => {
      const next = prev === "dark" ? "light" : "dark";
      window.localStorage.setItem(STORAGE_KEY, next);
      return next;
    });
  }

  return <Context.Provider value={{ theme, toggleTheme }}>{children}</Context.Provider>;
}

export function useTheme() {
  return useContext(Context);
}
