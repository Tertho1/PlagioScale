import React from 'react'
import './SimilarityMatrix.css'

function scoreToColor(v){
  // v expected in [0,1]
  const r = Math.round(255 * v)
  const g = Math.round(200 * (1 - v))
  const b = Math.round(100 * (1 - v))
  return `rgb(${r},${g},${b})`
}

export default function SimilarityMatrix({matrix, labels, onCellClick, maxDisplay=60}){
  const n = matrix ? matrix.length : 0
  if(!matrix || n===0) return <div>No similarity data</div>
  if(n > maxDisplay){
    return (
      <div>
        <p>Matrix too large to render in-grid ({n}×{n}). Use "Download CSV" or compute clusters.</p>
        <p>Showing first {maxDisplay} rows/cols as preview.</p>
        <SimilarityMatrixPreview matrix={matrix} labels={labels} onCellClick={onCellClick} previewSize={maxDisplay} />
      </div>
    )
  }

  return (
    <div className="smatrix-root">
      <div className="smatrix-grid" style={{gridTemplateColumns: `60px repeat(${n}, 1fr)`}}>
        <div className="smatrix-corner" />
        {labels.map((l, i)=> <div key={'h'+i} className="smatrix-header">{l}</div>)}

        {matrix.map((row, i) => (
          <React.Fragment key={'r'+i}>
            <div className="smatrix-rowheader">{labels[i]}</div>
            {row.map((cell, j)=> (
              <div key={`c-${i}-${j}`} className="smatrix-cell" title={`${labels[i]} ↔ ${labels[j]}: ${cell.toFixed(3)}`} onClick={()=>onCellClick && onCellClick(i,j,cell)} style={{background: scoreToColor(cell)}}>
                {i===j ? '—' : (cell>0.6 ? cell.toFixed(2) : '')}
              </div>
            ))}
          </React.Fragment>
        ))}
      </div>
    </div>
  )
}

function SimilarityMatrixPreview({matrix, labels, onCellClick, previewSize=60}){
  const n = Math.min(previewSize, matrix.length)
  const sub = matrix.slice(0,n).map(r=>r.slice(0,n))
  const labs = labels ? labels.slice(0,n) : Array.from({length:n}, (_,i)=>`S${i+1}`)
  return <SimilarityMatrix matrix={sub} labels={labs} onCellClick={onCellClick} maxDisplay={n} />
}
