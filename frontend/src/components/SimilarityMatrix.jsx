import PropTypes from "prop-types";
import React, { memo, useCallback } from 'react'
import './SimilarityMatrix.css'

// Band index drives CSS classes (light + dark variants live in SimilarityMatrix.css).
// Darker fills at higher bands give a second, luminance-based cue for color-blind users.
function bandIndex(v){
  if (v < 0.2) return 1
  if (v < 0.4) return 2
  if (v < 0.6) return 3
  if (v < 0.8) return 4
  return 5
}

function scoreLabel(v){
  if (v < 0.2) return 'Very low'
  if (v < 0.4) return 'Low'
  if (v < 0.6) return 'Medium'
  if (v < 0.8) return 'High'
  return 'Very high'
}

const ScoreLegend = memo(function ScoreLegend(){
  const bands = [
    { label: '0–20%', desc: 'Very low', band: 1 },
    { label: '20–40%', desc: 'Low', band: 2 },
    { label: '40–60%', desc: 'Medium', band: 3 },
    { label: '60–80%', desc: 'High', band: 4 },
    { label: '80–100%', desc: 'Very high', band: 5 },
  ]
  return (
    <div className="smatrix-legend" role="img" aria-label="Similarity score legend">
      {bands.map(b => (
        <div key={b.label} className="smatrix-legend-item">
          <span className={`smatrix-legend-swatch smatrix-band-${b.band}`} />
          <span className="smatrix-legend-label">{b.label}</span>
        </div>
      ))}
    </div>
  )
});

export default function SimilarityMatrix({matrix, labels, onCellClick, maxDisplay=60, threshold=0}){
  const n = matrix ? matrix.length : 0

  const handleCellKey = useCallback((e, i, j, cell) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onCellClick && onCellClick(i, j, cell);
      return;
    }
    // Roving focus: arrow keys move between cells
    const deltas = { ArrowUp: [-1, 0], ArrowDown: [1, 0], ArrowLeft: [0, -1], ArrowRight: [0, 1] };
    const d = deltas[e.key];
    if (!d) return;
    e.preventDefault();
    const ni = i + d[0], nj = j + d[1];
    if (ni < 0 || ni >= n || nj < 0 || nj >= n) return;
    const target = document.querySelector(
      `[data-cell="${ni}-${nj}"]`
    );
    if (target) {
      target.focus();
      if (!target.classList.contains('smatrix-cell-dimmed')) {
        // no-op; click still requires Enter/click to avoid accidental opens
      }
    }
  }, [onCellClick, n]);
  if(!matrix || n===0) return <div>No similarity data</div>
  if(n > maxDisplay){
    return (
      <div>
        <ScoreLegend />
        <p>Matrix too large to render in-grid ({n}&times;{n}). Showing a {maxDisplay}&times;{maxDisplay} preview below.</p>
        <p>Showing first {maxDisplay} rows/cols as preview.</p>
        <SimilarityMatrixPreview matrix={matrix} labels={labels} onCellClick={onCellClick} previewSize={maxDisplay} threshold={threshold} />
      </div>
    )
  }

  return (
    <div>
      <ScoreLegend />
      <div className="smatrix-root" role="grid" aria-label="Similarity matrix">
        <div className="smatrix-grid" style={{gridTemplateColumns: `60px repeat(${n}, 1fr)`}}>
          <div className="smatrix-corner" role="columnheader" />
          {labels.map((l, i)=> <div key={'h'+i} className="smatrix-header" role="columnheader" aria-label={l}>{l}</div>)}

          {matrix.map((row, i) => (
            <React.Fragment key={'r'+i}>
              <div className="smatrix-rowheader" role="rowheader" aria-label={labels[i]}>{labels[i]}</div>
              {row.map((cell, j)=> {
                const isDiag = i === j;
                const belowThreshold = !isDiag && threshold > 0 && cell < threshold;
                const band = bandIndex(cell);
                return (
                  <div
                    key={`c-${i}-${j}`}
                    data-cell={`${i}-${j}`}
                    className={`smatrix-cell smatrix-band-${band} ${belowThreshold ? 'smatrix-cell-dimmed' : ''}`}
                    role="gridcell"
                    tabIndex={isDiag ? -1 : 0}
                    title={`${labels[i]} ↔ ${labels[j]}: ${(cell * 100).toFixed(1)}% — ${scoreLabel(cell)}`}
                    aria-label={`Similarity ${labels[i]} to ${labels[j]}: ${(cell * 100).toFixed(1)} percent, ${scoreLabel(cell)}`}
                    onClick={() => !belowThreshold && onCellClick && onCellClick(i, j, cell)}
                    onKeyDown={(e) => !belowThreshold && handleCellKey(e, i, j, cell)}
                    style={belowThreshold ? { opacity: 0.25 } : undefined}
                  >
                      {isDiag ? '—' : cell.toFixed(2)}
                  </div>
                )
              })}
            </React.Fragment>
          ))}
        </div>
      </div>
    </div>
  )
}

SimilarityMatrix.propTypes = {
  matrix: PropTypes.arrayOf(PropTypes.arrayOf(PropTypes.number)),
  labels: PropTypes.arrayOf(PropTypes.string),
  onCellClick: PropTypes.func,
  maxDisplay: PropTypes.number,
  threshold: PropTypes.number,
};

function SimilarityMatrixPreview({matrix, labels, onCellClick, previewSize=60, threshold=0}){
  const n = Math.min(previewSize, matrix.length)
  const sub = matrix.slice(0,n).map(r=>r.slice(0,n))
  const labs = labels ? labels.slice(0,n) : Array.from({length:n}, (_,i)=>`S${i+1}`)
  return <SimilarityMatrix matrix={sub} labels={labs} onCellClick={onCellClick} maxDisplay={n} threshold={threshold} />
}

SimilarityMatrixPreview.propTypes = {
  matrix: PropTypes.arrayOf(PropTypes.arrayOf(PropTypes.number)),
  labels: PropTypes.arrayOf(PropTypes.string),
  onCellClick: PropTypes.func,
  previewSize: PropTypes.number,
  threshold: PropTypes.number,
};
