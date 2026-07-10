import { useCallback, useMemo, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import "../styles/portal.css";

export default function CollusionGraph({ matrix, labels, onNodeClick }) {
  const graphRef = useRef();
  const [hovered, setHovered] = useState(null);

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
      <div className="collusion-graph-container">
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
          width={600}
          height={400}
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
