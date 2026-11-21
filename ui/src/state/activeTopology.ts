import { createContext, useContext } from "react";
import type { Dispatch, SetStateAction } from "react";

export interface ActiveTopology {
  path?: string;
  name?: string;
  yamlText: string;
  pngBase64?: string;
  isDraft: boolean;
}

export interface ActiveTopologyContextValue {
  activeTopology: ActiveTopology | null;
  setActiveTopology: Dispatch<SetStateAction<ActiveTopology | null>>;
}

export const ActiveTopologyContext = createContext<ActiveTopologyContextValue | null>(null);

export function useActiveTopology(): ActiveTopologyContextValue {
  const value = useContext(ActiveTopologyContext);
  if (!value) throw new Error("ActiveTopologyContext provider is missing");
  return value;
}
