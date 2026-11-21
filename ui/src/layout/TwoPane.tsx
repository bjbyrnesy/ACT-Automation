import { useActiveTopology } from "../state/activeTopology";
import "./TwoPane.css";

export function TwoPane() {
  const { active } = useActiveTopology();
  const yaml =
    active.yamlText ||
    `# topology placeholder
# Preview / load a lab to populate this pane.`;

  return (
    <div className="two-pane" aria-label="Topology workspace">
      <section className="two-pane__yaml" aria-label="YAML">
        <div className="two-pane__label">YAML</div>
        <pre className="two-pane__mono">{yaml}</pre>
      </section>
      <section className="two-pane__diagram" aria-label="Diagram">
        <div className="two-pane__label">Diagram</div>
        <div className="two-pane__diagram-body">
          {active.pngBase64 ? (
            <img
              alt="Topology diagram"
              src={`data:image/png;base64,${active.pngBase64}`}
            />
          ) : (
            "Diagram placeholder"
          )}
        </div>
      </section>
    </div>
  );
}
