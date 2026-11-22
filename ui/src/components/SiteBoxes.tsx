import "./SiteBoxes.css";

type Props = {
  sites: string[];
  labName?: string;
};

/** Lightweight site map shown in the create wizard after Sites → Next. */
export function SiteBoxes({ sites, labName }: Props) {
  const boxes =
    sites.length > 0
      ? sites
      : [labName?.trim() || "Single site"];
  const multi = boxes.length > 1;

  return (
    <div className="site-boxes" aria-label="Site layout">
      <p className="site-boxes__caption">
        {multi
          ? `${boxes.length} sites — fabric fills in as you continue`
          : "Site layout — fabric fills in as you continue"}
      </p>
      <div
        className={
          multi ? "site-boxes__grid site-boxes__grid--multi" : "site-boxes__grid"
        }
      >
        {multi ? (
          <div className="site-boxes__core" aria-hidden="true">
            <span>Backbone</span>
          </div>
        ) : null}
        {boxes.map((name) => (
          <div key={name} className="site-boxes__site">
            <span className="site-boxes__site-label">
              {multi ? `Site ${name}` : name}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
