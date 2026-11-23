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

/** Circular magnifier: inspect labels without changing diagram zoom. */
const LOUPE_SIZE = 240;
const LOUPE_RADIUS = LOUPE_SIZE / 2;
const LOUPE_FACTOR = 2.75;

/** Tux hangs off the upper-right corner like a tag; text stays in the box. */
const HOST_TUX_W = 18;
const HOST_TUX_H = 21;
/** How far the tag hangs past the host border. */
const HOST_TUX_HANG = 8;
/** Inside-box corner reserved so clipped text cannot enter the tag zone. */
const HOST_TUX_RESERVE = 12;

const ROLE_FILL: Record<NodeRole, string> = {
  bb: "#0f766e",
  border: "#4338ca",
  spine: "#1d4ed8",
  leaf: "#2563eb",
  mleaf: "#7c3aed",
  host: "#c2410c",
};

/** Official Tux mark (Larry Ewing) as an upper-right host tag. */
function HostTux({ x, y }: { x: number; y: number }) {
  return (
    <image
      className="cv-diagram__host-tux"
      href={tuxUrl}
      x={x}
      y={y}
      width={HOST_TUX_W}
      height={HOST_TUX_H}
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
  const frameRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<HTMLDivElement>(null);
  const [zoom, setZoom] = useState(1);
  const [fitZoom, setFitZoom] = useState(1);
  const [loupeOn, setLoupeOn] = useState(false);
  const [loupePos, setLoupePos] = useState<{
    /** Loupe center relative to the frame (CSS px). */
    vx: number;
    vy: number;
    /** Pointer relative to the stage (CSS px) — what to center under the glass. */
    sx: number;
    sy: number;
  } | null>(null);
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
    setLoupeOn(false);
    setLoupePos(null);
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

  useEffect(() => {
    if (!loupeOn) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setLoupeOn(false);
        setLoupePos(null);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [loupeOn]);

  function clampZoom(value: number) {
    return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, value));
  }

  function updateLoupe(clientX: number, clientY: number) {
    if (!loupeOn) return;
    const frame = frameRef.current;
    const stage = stageRef.current;
    if (!frame || !stage) return;
    const frameRect = frame.getBoundingClientRect();
    const stageRect = stage.getBoundingClientRect();
    setLoupePos({
      vx: clientX - frameRect.left,
      vy: clientY - frameRect.top,
      sx: clientX - stageRect.left,
      sy: clientY - stageRect.top,
    });
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
    updateLoupe(event.clientX, event.clientY);
    setDrag({
      x: event.clientX,
      y: event.clientY,
      left: vp.scrollLeft,
      top: vp.scrollTop,
    });
  }

  function onPointerMove(event: React.PointerEvent) {
    if (drag) {
      const vp = viewportRef.current;
      if (vp) {
        vp.scrollLeft = drag.left - (event.clientX - drag.x);
        vp.scrollTop = drag.top - (event.clientY - drag.y);
      }
    }
    // After any pan scroll so stageRect matches what's under the pointer.
    updateLoupe(event.clientX, event.clientY);
  }

  function onPointerUp(event: React.PointerEvent) {
    const vp = viewportRef.current;
    if (vp?.hasPointerCapture(event.pointerId)) {
      vp.releasePointerCapture(event.pointerId);
    }
    setDrag(null);
  }

  function onPointerLeave() {
    setLoupePos(null);
  }

  function toggleLoupe() {
    setLoupeOn((on) => {
      if (on) setLoupePos(null);
      return !on;
    });
  }

  const pct = Math.round(zoom * 100);
  const hint = loupeOn
    ? "Loupe on · move to inspect · Esc to exit"
    : "⌘/Ctrl+wheel zoom · drag to pan";

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
        <button
          type="button"
          disabled={!layout}
          aria-pressed={loupeOn}
          aria-label="Magnifier"
          className={`cv-diagram__loupe-btn${loupeOn ? " is-active" : ""}`}
          onClick={toggleLoupe}
          title="Magnifier — inspect hostnames without zooming the whole diagram"
        >
          <svg
            className="cv-diagram__loupe-icon"
            viewBox="0 0 16 16"
            width="14"
            height="14"
            aria-hidden="true"
          >
            <circle
              cx="6.5"
              cy="6.5"
              r="4.25"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
            />
            <path
              d="M9.6 9.6 13.5 13.5"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.75"
              strokeLinecap="round"
            />
          </svg>
        </button>
        <span className="cv-diagram__hint">{hint}</span>
      </div>
      <div ref={frameRef} className="cv-diagram__frame">
        <div
          ref={viewportRef}
          className={`cv-diagram__viewport${drag ? " is-dragging" : ""}${
            loupeOn ? " is-loupe" : ""
          }`}
          onWheel={onWheel}
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
          onPointerCancel={onPointerUp}
          onPointerLeave={onPointerLeave}
        >
          {layout ? (
            <div
              ref={stageRef}
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
        {layout && loupeOn && loupePos ? (
          <div
            className="cv-diagram__loupe"
            style={{
              width: LOUPE_SIZE,
              height: LOUPE_SIZE,
              left: loupePos.vx - LOUPE_RADIUS,
              top: loupePos.vy - LOUPE_RADIUS,
            }}
            aria-hidden="true"
          >
            <div
              className="cv-diagram__loupe-inner"
              style={{
                width: layout.width * zoom,
                height: layout.height * zoom,
                transform: `translate(${LOUPE_RADIUS - loupePos.sx * LOUPE_FACTOR}px, ${LOUPE_RADIUS - loupePos.sy * LOUPE_FACTOR}px) scale(${LOUPE_FACTOR})`,
              }}
            >
              <SvgCanvas layout={layout} zoom={zoom} idPrefix="loupe-" decorative />
            </div>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function SvgCanvas({
  layout,
  zoom,
  idPrefix = "",
  decorative = false,
}: {
  layout: CvLayout;
  zoom: number;
  idPrefix?: string;
  decorative?: boolean;
}) {
  return (
    <svg
      className="cv-diagram__svg"
      width={layout.width * zoom}
      height={layout.height * zoom}
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      role={decorative ? "presentation" : "img"}
      aria-hidden={decorative ? true : undefined}
      aria-label={decorative ? undefined : layout.title}
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
        const titleX = node.x + node.w / 2;
        const titleY = node.y + (node.subtitle ? node.h / 2 - 4 : node.h / 2 + 4);
        const clipId = isHost
          ? `${idPrefix}host-text-${node.name.replace(/[^A-Za-z0-9_-]/g, "_")}`
          : null;
        // Text may use the full box except the top-right tag reserve.
        const textClipW = Math.max(8, node.w - 4 - (isHost ? HOST_TUX_RESERVE : 0));
        const textClipH = Math.max(8, node.h - 4);
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
            {isHost && clipId ? (
              <defs>
                <clipPath id={clipId}>
                  <rect
                    x={node.x + 2}
                    y={node.y + 2}
                    width={textClipW}
                    height={textClipH}
                  />
                </clipPath>
              </defs>
            ) : null}
            <g clipPath={clipId ? `url(#${clipId})` : undefined}>
              <text x={titleX} y={titleY} className="cv-diagram__node-title">
                {node.title}
              </text>
              {node.subtitle ? (
                <text
                  x={titleX}
                  y={node.y + node.h / 2 + 12}
                  className="cv-diagram__node-sub"
                >
                  {node.subtitle}
                </text>
              ) : null}
            </g>
            {isHost ? (
              <HostTux
                x={node.x + node.w - HOST_TUX_W + HOST_TUX_HANG}
                y={node.y - HOST_TUX_HANG}
              />
            ) : null}
            {node.ports.map((port) => (
              <g key={`${node.name}-${port.side}-${port.port}-${port.peerName}`}>
                <rect
                  x={port.x}
                  y={port.y}
                  width={22}
                  height={14}
                  className={`cv-diagram__port cv-diagram__port--${port.kind}`}
                />
                <text
                  x={port.x + 11}
                  y={port.y + 11}
                  className={`cv-diagram__port-label cv-diagram__port-label--${port.kind}`}
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
