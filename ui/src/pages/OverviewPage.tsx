import { useActiveTopology } from "../state/activeTopology";

export function OverviewPage() {
  const { active } = useActiveTopology();

  if (!active.yamlText) {
    return <p className="page-status">Loading lab…</p>;
  }

  return (
    <div className="ops-page">
      <p>
        Version <code>{active.name}</code>
        {active.path ? ` · ${active.path}` : ""}
      </p>
      <p className="page-status">
        Inventory and diagram below reflect this version. Use Grow, Hosts, or
        Deploy to change the lab.
      </p>
    </div>
  );
}
