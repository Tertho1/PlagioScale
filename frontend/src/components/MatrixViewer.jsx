import React from 'react'
import '../styles/portal.css'

export default function MatrixViewer({open, onClose, leftSubmission, rightSubmission, similarity}){
  if(!open) return null
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-panel" onClick={e=>e.stopPropagation()}>
        <div className="toolbar" style={{justifyContent:'space-between', alignItems:'flex-start'}}>
          <div>
            <div className="section-label" style={{marginBottom:10}}>Comparison details</div>
            <h3 className="section-title" style={{marginBottom:8}}>Similarity score: {similarity?.toFixed(3)}</h3>
            <p className="section-copy">Review the two submissions side by side to understand why this pair was flagged.</p>
          </div>
          <button className="button-ghost" onClick={onClose}>Close</button>
        </div>

        <div className="grid-2" style={{marginTop:18}}>
          <div className="surface" style={{padding:18, background:'rgba(255,255,255,.92)'}}>
            <div className="field-title" style={{marginBottom:10}}>Left submission</div>
            <pre style={{whiteSpace:'pre-wrap', maxHeight:420, overflow:'auto', background:'rgba(37,99,235,.05)', padding:16, borderRadius:14, margin:0, lineHeight:1.7}}>{leftSubmission?.text || leftSubmission?.snippet || 'No text available'}</pre>
          </div>
          <div className="surface" style={{padding:18, background:'rgba(255,255,255,.92)'}}>
            <div className="field-title" style={{marginBottom:10}}>Right submission</div>
            <pre style={{whiteSpace:'pre-wrap', maxHeight:420, overflow:'auto', background:'rgba(124,58,237,.05)', padding:16, borderRadius:14, margin:0, lineHeight:1.7}}>{rightSubmission?.text || rightSubmission?.snippet || 'No text available'}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}
