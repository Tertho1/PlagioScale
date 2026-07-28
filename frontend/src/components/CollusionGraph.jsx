import PropTypes from "prop-types";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import "../styles/portal.css";

export default function CollusionGraph({ matrix, labels, onNodeClick }) {
  const graphRef = useRef();
  const [hovered, setHovered] = useState(null);
  const [dims, setDims] = useState({ width: 600, height: 400 });

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const obs = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        setDims({ width: Math.max(300, width), height: Math.max(250, width * 0.6) });
      }
    });
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const graphData = useMemo(() => {
    if (!matrix || !labels || labels.length === 0) {
      return { nodes: [], links: [] };
    }

    const nodes = labels.map((label, i) => ({
      id: i,
      name: label,
      val: 3,
    }));

    const links = [];
    const threshold = 0.5;

    for (let i = 0; i < matrix.length; i++) {
      for (let j = i + 1; j < matrix[i].length; j++) {
        const score = matrix[i][j];
        if (score >= threshold) {
          links.push({
            source: i,
            target: j,
            score,
            color: `rgba(220, 38, 38, ${Math.max(0.3, score)})`,
            width: Math.max(1, score * 4),
          });
}

CollusionGraph.propTypes = {
  matrix: PropTypes.arrayOf(PropTypes.arrayOf(PropTypes.number)),
  labels: PropTypes.arrayOf(PropTypes.string),
  onNodeClick: PropTypes.func,
};
      }
    }

    return { nodes, links };
  }, [matrix, labels]);

  const handleClick = useCallback(
    (node) => {
      if (onNodeClick) onNodeClick(node.id);
    },
    [onNodeClick],
  );

  if (!matrix || !labels || labels.length < 3) {
    return (
      <div className="empty-state" style={{ padding: 40, textAlign: "center" }}>
        Upload at least 3 submissions and compute similarity to see the collusion graph.
      </div>
    );
  }

  if (graphData.links.length === 0) {
    return (
      <div className="empty-state" style={{ padding: 40, textAlign: "center" }}>
        No collusion detected (no pairs above threshold).
      </div>
    );
  }

  return (
    <div className="collusion-graph-root">
      <div className="section-label">Collusion graph</div>
      <p className="section-copy">
        Nodes with similarity ≥ 0.5 are connected. Red edge intensity = similarity strength.
      </p>
      <div className="collusion-graph-container" ref={containerRef}>
        <ForceGraph2D
          ref={graphRef}
          graphData={graphData}
          nodeLabel="name"
          nodeColor={() => "#2563eb"}
          nodeRelSize={6}
          linkColor={(link) => link.color}
          linkWidth={(link) => link.width}
          linkDirectionalParticles={1}
          linkDirectionalParticleWidth={2}
          onNodeClick={handleClick}
          onNodeHover={(node) => setHovered(node?.name || null)}
          width={dims.width}
          height={dims.height}
        />
      </div>
      {hovered && (
        <div className="collusion-graph-hover" style={{ marginTop: 8, fontSize: "0.85rem", color: "var(--text-soft)" }}>
          Hovering: {hovered}
        </div>
      )}
    </div>
  );
}
