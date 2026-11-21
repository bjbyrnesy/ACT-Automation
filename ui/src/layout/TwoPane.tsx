import "./TwoPane.css";

export function TwoPane() {
  return (
    <div className="two-pane" aria-label="Topology workspace">
      <section className="two-pane__yaml" aria-label="YAML">
        <div className="two-pane__label">YAML</div>
        <pre className="two-pane__mono">
          {`# topology placeholder
# Preview / load a lab to populate this pane.`}
        </pre>
      </section>
      <section className="two-pane__diagram" aria-label="Diagram">
        <div className="two-pane__label">Diagram</div>
        <div className="two-pane__diagram-body">Diagram placeholder</div>
      </section>
    </div>
  );
}
