import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { parseTopologyGraph } from "../topo/graph";
import { layoutCvDiagram, type CvLayout } from "../topo/cvLayout";
import type { NodeRole } from "../topo/summary";
// Official Tux (Larry Ewing) — see ui/src/assets/TUX_ATTRIBUTION.txt
import tuxUrl from "../assets/tux.svg";
import "./CvDiagram.css";

type Props = {
  yamlText: string;
  emptyLabel?: string;
};

const ZOOM_STEP = 1.25;
const MIN_ZOOM = 0.2;
const MAX_ZOOM = 4;

/** Reserved left strip for Tux so hostname text never draws under the logo. */
const HOST_ICON_SLOT = 22;
const HOST_ICON_PAD = 3;
const HOST_ICON_W = 16;
const HOST_ICON_H = 19;

const ROLE_FILL: Record<NodeRole, string> = {
  bb: "#0f766e",
  border: "#4338ca",
  spine: "#1d4ed8",
  leaf: "#2563eb",
  mleaf: "#7c3aed",
  host: "#c2410c",
};

/** Official Tux mark (Larry Ewing) sized for narrow host boxes. */
function HostTux({ x, y }: { x: number; y: number }) {
  return (
    <image
      className="cv-diagram__host-tux"
      href={tuxUrl}
      x={x}
      y={y}
      width={HOST_ICON_W}
      height={HOST_ICON_H}
      preserveAspectRatio="xMidYMid meet"
      aria-hidden="true"
    />
  );
}

export function CvDiagram({
  yamlText,
  emptyLabel = "No topology to draw.",
}: Props) {
  const layout = useMemo(() => {
    const graph = parseTopologyGraph(yamlText);
    return graph ? layoutCvDiagram(graph) : null;
  }, [yamlText]);

  const viewportRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [fitZoom, setFitZoom] = useState(1);
  const [drag, setDrag] = useState<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);

  const computeFit = useCallback(() => {
    const vp = viewportRef.current;
    if (!vp || !layout) return 1;
    const pad = 24;
    const availW = Math.max(40, vp.clientWidth - pad);
    const availH = Math.max(40, vp.clientHeight - pad);
    return Math.min(1, availW / layout.width, availH / layout.height);
  }, [layout]);

  const applyFit = useCallback(() => {
    const next = computeFit();
    setFitZoom(next);
    setZoom(next);
    const vp = viewportRef.current;
    if (vp) {
      vp.scrollLeft = 0;
      vp.scrollTop = 0;
    }
  }, [computeFit]);

  useEffect(() => {
    setZoom(1);
    setFitZoom(1);
  }, [yamlText]);

  useEffect(() => {
    if (!layout) return;
    applyFit();
  }, [layout, applyFit]);

  useEffect(() => {
    const vp = viewportRef.current;
    if (!vp || !layout) return;
    const ro = new ResizeObserver(() => {
      const nextFit = computeFit();
      setFitZoom(nextFit);
      setZoom((z) => (Math.abs(z - fitZoom) < 0.02 ? nextFit : z));
    });
    ro.observe(vp);
    return () => ro.disconnect();
  }, [layout, computeFit, fitZoom]);

  function clampZoom(value: number) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  }

  function onWheel(event: React.WheelEvent) {
    if (!layout) return;
    if (!(event.ctrlKey || event.metaKey)) return;
    event.preventDefault();
    const factor = event.deltaY < 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
    setZoom((z) => clampZoom(z * factor));
  }

  function onPointerDown(event: React.PointerEvent) {
    if (!layout || event.button !== 0) return;
    const vp = viewportRef.current;
    if (!vp) return;
    vp.setPointerCapture(event.pointerId);
    setDrag({
      x: event.clientX,
      y: event.clientY,
      left: vp.scrollLeft,
      top: vp.scrollTop,
    });
  }

  function onPointerMove(event: React.PointerEvent) {
    if (!drag) return;
    const vp = viewportRef.current;
    if (!vp) return;
    vp.scrollLeft = drag.left - (event.clientX - drag.x);
    vp.scrollTop = drag.top - (event.clientY - drag.y);
  }

  function onPointerUp(event: React.PointerEvent) {
    const vp = viewportRef.current;
    if (vp?.hasPointerCapture(event.pointerId)) {
      vp.releasePointerCapture(event.pointerId);
    }
    setDrag(null);
  }

  const pct = Math.round(zoom * 100);

  return (
    <div className="cv-diagram">
      <div className="cv-diagram__toolbar" role="toolbar" aria-label="Diagram zoom">
        <button type="button" disabled={!layout} onClick={applyFit}>
          Fit
        </button>
        <button
          type="button"
          disabled={!layout}
          onClick={() => setZoom((z) => clampZoom(z / ZOOM_STEP))}
        >
          −
        </button>
        <span className="cv-diagram__pct" aria-live="polite">
          {layout ? `${pct}%` : "—"}
        </span>
        <button
          type="button"
          disabled={!layout}
          onClick={() => setZoom((z) => clampZoom(z * ZOOM_STEP))}
        >
          +
        </button>
        <button
          type="button"
          disabled={!layout}
          onClick={() => setZoom(1)}
          title="Native resolution"
        >
          100%
        </button>
        <span className="cv-diagram__hint">⌘/Ctrl+wheel zoom · drag to pan</span>
      </div>
      <div
        ref={viewportRef}
        className={`cv-diagram__viewport${drag ? " is-dragging" : ""}`}
        onWheel={onWheel}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
      >
        {layout ? (
          <div
            className="cv-diagram__stage"
            style={{
              width: layout.width * zoom,
              height: layout.height * zoom,
            }}
          >
            <SvgCanvas layout={layout} zoom={zoom} />
          </div>
        ) : (
          <span className="cv-diagram__empty">{emptyLabel}</span>
        )}
      </div>
    </div>
  );
}

function SvgCanvas({ layout, zoom }: { layout: CvLayout; zoom: number }) {
  return (
    <svg
      className="cv-diagram__svg"
      width={layout.width * zoom}
      height={layout.height * zoom}
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role="img"
      aria-label={layout.title}
    >
      <rect
        x={0}
        y={0}
        width={layout.width}
        height={layout.height}
        className="cv-diagram__canvas"
      />
      <text x={layout.width / 2} y={22} className="cv-diagram__title">
        {layout.title}
      </text>

      {layout.domains
        .filter((d) => d.kind === "site")
        .map((d) => (
          <g key={d.id}>
            <rect
              x={d.x}
              y={d.y}
              width={d.w}
              height={d.h}
              className="cv-diagram__site"
            />
            <text x={d.x + 10} y={d.y + 16} className="cv-diagram__site-label">
              {d.label}
            </text>
          </g>
        ))}

      {layout.domains
        .filter((d) => d.kind === "mlag")
        .map((d) => (
          <g key={d.id}>
            <rect
              x={d.x}
              y={d.y}
              width={d.w}
              height={d.h}
              className="cv-diagram__mlag"
            />
            <text
              x={d.x + d.w / 2}
              y={d.y - 4}
              className="cv-diagram__mlag-label"
            >
              {d.label}
            </text>
          </g>
        ))}

      {layout.links.map((link) => (
        <polyline
          key={link.id}
          points={link.points.map((p) => `${p.x},${p.y}`).join(" ")}
          className={`cv-diagram__link cv-diagram__link--${link.kind}`}
        />
      ))}

      {layout.bundles.map((b) => (
        <ellipse
          key={b.id}
          cx={b.cx}
          cy={b.cy}
          rx={b.rx}
          ry={b.ry}
          className="cv-diagram__po"
        />
      ))}

      {layout.nodes.map((node) => {
        const isHost = node.role === "host";
        const textLeft = node.x + HOST_ICON_SLOT;
        const textWidth = Math.max(8, node.w - HOST_ICON_SLOT - 4);
        const titleX = isHost ? textLeft : node.x + node.w / 2;
        const titleY = node.y + (node.subtitle ? node.h / 2 - 4 : node.h / 2 + 4);
        const clipId = isHost
          ? `host-text-${node.name.replace(/[^A-Za-z0-9_-]/g, "_")}`
          : null;
        return (
          <g key={node.name}>
            <rect
              x={node.x}
              y={node.y}
              width={node.w}
              height={node.h}
              rx={isHost ? 6 : 0}
              fill={ROLE_FILL[node.role]}
              className={
                isHost
                  ? "cv-diagram__node cv-diagram__node--host"
                  : "cv-diagram__node"
              }
            />
            {isHost ? (
              <>
                <HostTux
                  x={node.x + HOST_ICON_PAD}
                  y={node.y + (node.h - HOST_ICON_H) / 2}
                />
                <clipPath id={clipId!}>
                  <rect
                    x={textLeft}
                    y={node.y}
                    width={textWidth}
                    height={node.h}
                  />
                </clipPath>
              </>
            ) : null}
            <g clipPath={clipId ? `url(#${clipId})` : undefined}>
              <text
                x={titleX}
                y={titleY}
                className={
                  isHost
                    ? "cv-diagram__node-title cv-diagram__node-title--host"
                    : "cv-diagram__node-title"
                }
              >
                {node.title}
              </text>
              {node.subtitle ? (
                <text
                  x={titleX}
                  y={node.y + node.h / 2 + 12}
                  className={
                    isHost
                      ? "cv-diagram__node-sub cv-diagram__node-sub--host"
                      : "cv-diagram__node-sub"
                  }
                >
                  {node.subtitle}
                </text>
              ) : null}
            </g>
            {node.ports.map((port) => (
              <g key={`${node.name}-${port.side}-${port.port}-${port.peerName}`}>
                <rect
                  x={port.x}
                  y={port.y}
                  width={22}
                  height={14}
                  className="cv-diagram__port"
                />
                <text
                  x={port.x + 11}
                  y={port.y + 11}
                  className="cv-diagram__port-label"
                >
                  {port.port}
                </text>
              </g>
            ))}
          </g>
        );
      })}
    </svg>
  );
}
