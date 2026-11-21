import { useActiveTopology } from "../state/activeTopology";
import "./TopologyPane.css";

export function TopologyPane() {
  const { activeTopology } = useActiveTopology();
  return (
    <div className="topology-pane" aria-label="Topology workspace">
      <section className="topology-pane__panel" aria-label="YAML">
        <div className="topology-pane__label">YAML{activeTopology?.isDraft ? " · Draft" : ""}</div>
        <pre className="topology-pane__yaml">{activeTopology?.yamlText || "Preview a topology to see its YAML."}</pre>
      </section>
      <section className="topology-pane__panel" aria-label="Diagram">
        <div className="topology-pane__label">Diagram</div>
        <div className="topology-pane__diagram">
          {activeTopology?.pngBase64 ? (
            <img src={`data:image/png;base64,${activeTopology.pngBase64}`} alt="Topology diagram" />
          ) : (
            <span>{activeTopology ? "Graphviz image unavailable." : "Preview a topology to see its diagram."}</span>
          )}
        </div>
      </section>
    </div>
  );
}
