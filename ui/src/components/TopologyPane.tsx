import { useMemo, useState } from "react";
import { useLocation } from "react-router-dom";
import { useActiveTopology } from "../state/activeTopology";
import { useCreateWizard } from "../state/createWizard";
import { parseTopologyGraph } from "../topo/graph";
import { roleLabel, type NodeRole, type TopologySummary } from "../topo/summary";
import { CvDiagram } from "./CvDiagram";
import { SiteBoxes } from "./SiteBoxes";
import "./TopologyPane.css";

const ROLE_ORDER: NodeRole[] = ["bb", "border", "spine", "leaf", "mleaf", "host"];

export function TopologyPane() {
  const { pathname } = useLocation();
  const { active } = useActiveTopology();
  const { wizard } = useCreateWizard();
  const creating = pathname === "/new" || pathname.startsWith("/new/");
  const [showYaml, setShowYaml] = useState(false);
  const summary = useMemo(
    () =>
      parseTopologyGraph(active.yamlText, { mgmtIps: active.mgmtIps })?.summary ??
      null,
    [active.yamlText, active.mgmtIps],
  );
  const hasYaml = Boolean(active.yamlText);

  return (
    <div className="topology-pane" aria-label="Topology workspace">
      <section className="topology-pane__side" aria-label="Topology summary">
        <div className="topology-pane__label">
          {creating
            ? "Selections"
            : `Inventory${active.isDraft ? " · Draft" : ""}${active.name ? ` · ${active.name}` : ""}`}
        </div>
        <div className="topology-pane__side-body">
          {creating && wizard ? (
            <WizardSelections />
          ) : !summary ? (
            <p className="topology-pane__muted">
              Open a topology to see nodes and the diagram.
            </p>
          ) : (
            <InventoryBody summary={summary} />
          )}

          {creating && summary ? (
            <ul className="topology-pane__role-chips" aria-label="Role counts">
              {ROLE_ORDER.filter((role) => summary.byRole[role] > 0).map(
                (role) => (
                  <li key={role}>
                    <span>{roleLabel(role)}</span>
                    <strong>{summary.byRole[role]}</strong>
                  </li>
                ),
              )}
            </ul>
          ) : null}

          {hasYaml && !creating ? (
            <div className="topology-pane__yaml-toggle">
              <button type="button" onClick={() => setShowYaml((v) => !v)}>
                {showYaml ? "Hide YAML" : "Show YAML"}
              </button>
              {showYaml ? (
                <pre className="topology-pane__yaml">{active.yamlText}</pre>
              ) : null}
            </div>
          ) : null}
        </div>
      </section>

      <section className="topology-pane__diagram-panel" aria-label="Diagram">
        <div className="topology-pane__label">
          Diagram
          {creating && wizard?.sitesCommitted && !hasYaml ? " · sites" : ""}
        </div>
        {hasYaml ? (
          <CvDiagram
            yamlText={active.yamlText}
            mgmtIps={active.mgmtIps}
            emptyLabel="Topology YAML did not parse into a diagram."
          />
        ) : creating && wizard?.sitesCommitted ? (
          <SiteBoxes
            sites={wizard.sites}
            labName={
              wizard.facts.find((fact) => fact.label === "Lab")?.value
            }
          />
        ) : (
          <div className="topology-pane__diagram-empty">
            {creating
              ? "Complete Identity, then Sites — the diagram updates when you hit Next."
              : "Open a topology to see its diagram."}
          </div>
        )}
      </section>
    </div>
  );
}

function WizardSelections() {
  const { wizard } = useCreateWizard();
  if (!wizard) return null;

  return (
    <div className="topology-pane__wizard">
      <p className="topology-pane__wizard-step">
        Step {wizard.stepIndex + 1} of {wizard.totalSteps}: {wizard.stepTitle}
      </p>
      {wizard.facts.length === 0 ? (
        <p className="topology-pane__muted">
          Your choices will collect here as you go.
        </p>
      ) : (
        <dl className="topology-pane__meta">
          {wizard.facts.map((fact) => (
            <div key={`${fact.step}-${fact.label}`} className="topology-pane__fact">
              <dt>{fact.label}</dt>
              <dd className="topology-pane__fact-value">{fact.value}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function InventoryBody({ summary }: { summary: TopologySummary }) {
  return (
    <>
      <dl className="topology-pane__meta">
        {summary.fabricMode ? (
          <>
            <dt>Mode</dt>
            <dd>{summary.fabricMode}</dd>
          </>
        ) : null}
        {summary.useCase ? (
          <>
            <dt>Use case</dt>
            <dd>{summary.useCase}</dd>
          </>
        ) : null}
        <dt>Nodes</dt>
        <dd>{summary.nodeCount}</dd>
        <dt>Links</dt>
        <dd>{summary.linkCount}</dd>
        <dt>Sites</dt>
        <dd>
          {summary.sites.filter((s) => s !== "core" && s !== "fabric").length ||
            1}
        </dd>
      </dl>

      <ul className="topology-pane__role-chips" aria-label="Role counts">
        {ROLE_ORDER.filter((role) => summary.byRole[role] > 0).map((role) => (
          <li key={role}>
            <span>{roleLabel(role)}</span>
            <strong>{summary.byRole[role]}</strong>
          </li>
        ))}
      </ul>

      <div className="topology-pane__sites">
        {summary.sites.map((site) => (
          <div key={site} className="topology-pane__site">
            <h3>
              {site === "core"
                ? "Core / backbone"
                : site === "fabric"
                  ? "Fabric"
                  : `Site ${site}`}
            </h3>
            <ul>
              {summary.bySite[site].map((node) => (
                <li key={node.name}>
                  <span className="topology-pane__node-name">{node.name}</span>
                  <span className="topology-pane__node-meta">
                    {roleLabel(node.role)}
                    {node.ipAddr ? ` · ${node.ipAddr}` : ""}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </>
  );
}
