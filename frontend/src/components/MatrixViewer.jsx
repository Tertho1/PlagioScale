import React, { useCallback, useEffect, useRef } from 'react'
import { getAuthHeaders } from '../utils/auth'
import { showToast } from './Toast'
import '../styles/portal.css'

const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

export default function MatrixViewer({open, onClose, leftSubmission, rightSubmission, similarity, batchId}){
  const modalRef = useRef(null);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onClose();
    }
    if (e.key === 'Tab' && modalRef.current) {
      const focusable = modalRef.current.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      );
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault();
          last.focus();
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    }
  }, [onClose]);

  useEffect(() => {
    if (!open) return;
    document.addEventListener('keydown', handleKeyDown);
    const timer = setTimeout(() => {
      if (modalRef.current) {
        const firstBtn = modalRef.current.querySelector('button');
        if (firstBtn) firstBtn.focus();
      }
    }, 100);
    return () => {
      document.removeEventListener('keydown', handleKeyDown);
      clearTimeout(timer);
    };
  }, [open, handleKeyDown]);

  if(!open) return null
  return (
    <div className="modal-overlay" onClick={onClose} role="dialog" aria-modal="true" aria-label="Comparison details">
      <div className="modal-panel" onClick={e=>e.stopPropagation()} ref={modalRef}>
        <div className="toolbar" style={{justifyContent:'space-between', alignItems:'flex-start'}}>
          <div>
            <div className="section-label" style={{marginBottom:10}}>Comparison details</div>
            <h3 className="section-title" style={{marginBottom:8}}>Similarity score: {similarity?.toFixed(3)}</h3>
            <p className="section-copy">Review the two submissions side by side to understand why this pair was flagged.</p>
          </div>
          <div style={{display: 'flex', gap: 8, alignItems: 'center'}}>
            <button className="button-ghost" onClick={async () => {
              if (!leftSubmission?.submission_id || !rightSubmission?.submission_id || !batchId) return;
              try {
                const res = await fetch(
                  `${API_BASE}/portal/report/${batchId}/${leftSubmission.submission_id}/${rightSubmission.submission_id}`,
                  { headers: await getAuthHeaders(), credentials: "include" }
                );
                if (!res.ok) throw new Error("Failed to generate report");
                const blob = await res.blob();
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url; a.download = `report_${batchId.slice(0,8)}.pdf`;
                a.click(); URL.revokeObjectURL(url);
              } catch (e) {
                showToast(e.message || "Download failed", "error");
              }
            }} aria-label="Download PDF report">Download Report</button>
            <button className="button-ghost" onClick={onClose} aria-label="Close comparison">Close</button>
          </div>
        </div>

        <div className="grid-2" style={{marginTop:18}}>
          <div className="surface" style={{padding:18, background:'rgba(255,255,255,.92)'}}>
            <div className="field-title" style={{marginBottom:4}}>Left submission</div>
            <div style={{fontSize:13, color:'#475569', marginBottom:8, lineHeight:1.6}}>
              <div><strong>Roll:</strong> {leftSubmission?.roll || "—"}</div>
              <div><strong>Name:</strong> {leftSubmission?.name || "—"}</div>
              <div><strong>File:</strong> {leftSubmission?.filename ? leftSubmission.filename.split("_").slice(3).join("_") : "—"}</div>
            </div>
            <pre style={{whiteSpace:'pre-wrap', maxHeight:380, overflow:'auto', background:'rgba(37,99,235,.05)', padding:16, borderRadius:14, margin:0, lineHeight:1.7}}>{leftSubmission?.text || leftSubmission?.snippet || 'No text available'}</pre>
          </div>
          <div className="surface" style={{padding:18, background:'rgba(255,255,255,.92)'}}>
            <div className="field-title" style={{marginBottom:4}}>Right submission</div>
            <div style={{fontSize:13, color:'#475569', marginBottom:8, lineHeight:1.6}}>
              <div><strong>Roll:</strong> {rightSubmission?.roll || "—"}</div>
              <div><strong>Name:</strong> {rightSubmission?.name || "—"}</div>
              <div><strong>File:</strong> {rightSubmission?.filename ? rightSubmission.filename.split("_").slice(3).join("_") : "—"}</div>
            </div>
            <pre style={{whiteSpace:'pre-wrap', maxHeight:380, overflow:'auto', background:'rgba(124,58,237,.05)', padding:16, borderRadius:14, margin:0, lineHeight:1.7}}>{rightSubmission?.text || rightSubmission?.snippet || 'No text available'}</pre>
          </div>
        </div>
      </div>
    </div>
  )
}
