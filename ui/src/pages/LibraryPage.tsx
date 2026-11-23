import { useEffect } from "react";
import { Link } from "react-router-dom";
import { useActiveTopology } from "../state/activeTopology";
import "./LibraryPage.css";

export function LibraryPage() {
  const { clearActive } = useActiveTopology();

  useEffect(() => {
    clearActive();
  }, [clearActive]);

  return (
    <div className="library-page">
      <div className="library-page__head">
        <div>
          <h1>Topologies</h1>
          <p>
            Pick a topology name in the sidebar to open it. Click another name
            anytime to switch.
          </p>
        </div>
        <div className="library-page__actions">
          <Link className="btn-primary library-page__new" to="/new">
            New lab
          </Link>
        </div>
      </div>
    </div>
  );
}
