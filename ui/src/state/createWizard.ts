import {
  createContext,
  createElement,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type WizardFact = {
  label: string;
  value: string;
  /** Step id that owns this fact. */
  step: string;
};

export type CreateWizardSnapshot = {
  stepIndex: number;
  stepId: string;
  stepTitle: string;
  totalSteps: number;
  facts: WizardFact[];
  previewing: boolean;
  /** Site labels to draw once the Sites step is completed. */
  sites: string[];
  /** True after the user leaves the Sites step (Next). */
  sitesCommitted: boolean;
};

type CreateWizardContextValue = {
  wizard: CreateWizardSnapshot | null;
  setWizard: (next: CreateWizardSnapshot | null) => void;
};

const CreateWizardContext = createContext<CreateWizardContextValue | null>(
  null,
);

export function CreateWizardProvider({ children }: { children: ReactNode }) {
  const [wizard, setWizard] = useState<CreateWizardSnapshot | null>(null);
  const value = useMemo(() => ({ wizard, setWizard }), [wizard]);
  return createElement(CreateWizardContext.Provider, { value }, children);
}

export function useCreateWizard(): CreateWizardContextValue {
  const ctx = useContext(CreateWizardContext);
  if (!ctx) {
    throw new Error("useCreateWizard requires CreateWizardProvider");
  }
  return ctx;
}
