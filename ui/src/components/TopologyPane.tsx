import { useActiveTopology } from "../state/activeTopology";
import "./TopologyPane.css";

export function TopologyPane() {
  const { active } = useActiveTopology();
  const hasYaml = Boolean(active.yamlText);
  return (
    <div className="topology-pane" aria-label="Topology workspace">
      <section className="topology-pane__panel" aria-label="YAML">
        <div className="topology-pane__label">
          YAML{active.isDraft ? " · Draft" : ""}
        </div>
        <pre className="topology-pane__yaml">
          {active.yamlText || "Preview a topology to see its YAML."}
        </pre>
      </section>
      <section className="topology-pane__panel" aria-label="Diagram">
        <div className="topology-pane__label">Diagram</div>
        <div className="topology-pane__diagram">
          {active.pngBase64 ? (
            <img
              src={`data:image/png;base64,${active.pngBase64}`}
              alt="Topology diagram"
            />
          ) : (
            <span>
              {hasYaml
                ? "Graphviz image unavailable."
                : "Preview a topology to see its diagram."}
            </span>
          )}
        </div>
      </section>
    </div>
  );
}
