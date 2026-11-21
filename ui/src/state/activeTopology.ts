import {
  createContext,
  createElement,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ActiveTopology = {
  path: string | null;
  name: string | null;
  yamlText: string;
  pngBase64: string | null;
  isDraft: boolean;
};

type ActiveTopologyContextValue = {
  active: ActiveTopology;
  setActive: (next: ActiveTopology) => void;
  clearActive: () => void;
};

const EMPTY: ActiveTopology = {
  path: null,
  name: null,
  yamlText: "",
  pngBase64: null,
  isDraft: false,
};

const ActiveTopologyContext = createContext<ActiveTopologyContextValue | null>(
  null,
);

export function ActiveTopologyProvider({ children }: { children: ReactNode }) {
  const [active, setActive] = useState<ActiveTopology>(EMPTY);
  const value = useMemo(
    () => ({
      active,
      setActive,
      clearActive: () => setActive(EMPTY),
    }),
    [active],
  );
  return createElement(ActiveTopologyContext.Provider, { value }, children);
}

export function useActiveTopology(): ActiveTopologyContextValue {
  const ctx = useContext(ActiveTopologyContext);
  if (!ctx) {
    throw new Error("useActiveTopology requires ActiveTopologyProvider");
  }
  return ctx;
}
