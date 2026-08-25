import PropTypes from "prop-types";
import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { API_BASE } from '../utils/config'
import { getAuthHeaders } from '../utils/auth'
import { showToast } from './Toast'
import '../styles/portal.css'

function findCommonNgrams(textA, textB, n = 4) {
  if (!textA || !textB) return [];
  const wordsA = textA.toLowerCase().split(/\s+/);
  const wordsB = textB.toLowerCase().split(/\s+/);
  const matches = [];
  const seen = new Set();

  for (let i = 0; i <= wordsA.length - n; i++) {
    const gram = wordsA.slice(i, i + n).join(' ');
    if (gram.length < 10) continue;
    for (let j = 0; j <= wordsB.length - n; j++) {
      const gramB = wordsB.slice(j, j + n).join(' ');
      if (gram === gramB && !seen.has(gram)) {
        seen.add(gram);
        matches.push({ text: wordsA.slice(i, i + n).join(' '), posA: i, posB: j, len: n });
        break;
      }
    }
  }
  return matches;
}

function HighlightedText({ text, matches, side, color }) {
  const parts = useMemo(() => {
    if (!text || !matches.length) return [{ text, highlight: false }];
    const words = text.split(/(\s+)/);
    const highlights = new Set();
    matches.forEach(m => {
      const startIdx = side === 'left' ? m.posA : m.posB;
      for (let k = startIdx; k < startIdx + m.len; k++) highlights.add(k);
    });
    const result = [];
    let current = '';
    let currentHighlight = false;
    let wordIdx = 0;
    for (let i = 0; i < words.length; i++) {
      const isSpace = /^\s+$/.test(words[i]);
      if (isSpace) {
        current += words[i];
      } else {
        const hl = highlights.has(wordIdx);
        if (hl !== currentHighlight && current) {
          result.push({ text: current, highlight: currentHighlight });
          current = '';
        }
        currentHighlight = hl;
        current += words[i];
        wordIdx++;
      }
    }
    if (current) result.push({ text: current, highlight: currentHighlight });
    return result;
  }, [text, matches, side]);

  return (
    <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 380, overflow: 'auto', background: 'rgba(255,255,255,.6)', padding: 16, borderRadius: 14, margin: 0, lineHeight: 1.7, fontSize: 13 }}>
      {parts.map((p, i) => p.highlight ? (
        <mark key={i} style={{ background: color, borderRadius: 3, padding: '1px 2px' }}>{p.text}</mark>
      ) : p.text)}
    </pre>
  );
}

HighlightedText.propTypes = {
  text: PropTypes.string,
  matches: PropTypes.array,
  side: PropTypes.oneOf(['left', 'right']),
  color: PropTypes.string,
};

export default function MatrixViewer({open, onClose, leftSubmission, rightSubmission, similarity, batchId, loading}){
  const dialogRef = useRef(null);
  const [annotations, setAnnotations] = useState([]);
  const [annotationText, setAnnotationText] = useState('');
  const [savingAnnotation, setSavingAnnotation] = useState(false);

  const handleDialogClose = useCallback(() => {
    onClose();
    setAnnotations([]);
    setAnnotationText('');
  }, [onClose]);

  const commonMatches = useMemo(() => {
    const textA = leftSubmission?.text || '';
    const textB = rightSubmission?.text || '';
    return findCommonNgrams(textA, textB, 4);
  }, [leftSubmission?.text, rightSubmission?.text]);

  const loadAnnotations = useCallback(async () => {
    const subId = leftSubmission?.submission_id || rightSubmission?.submission_id;
    if (!subId) return;
    try {
      const res = await fetch(`${API_BASE}/portal/annotations/${subId}`, {
        headers: await getAuthHeaders(),
        credentials: 'include',
      });
      if (res.ok) {
        const data = await res.json();
        setAnnotations(data.annotations || []);
      }
    } catch (e) { console.warn("Failed to load annotations:", e); }
  }, [leftSubmission?.submission_id, rightSubmission?.submission_id]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      dialog.showModal();
      loadAnnotations();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open, loadAnnotations]);

  async function handleAddAnnotation() {
    const subId = leftSubmission?.submission_id || rightSubmission?.submission_id;
    if (!subId || !annotationText.trim()) return;
    setSavingAnnotation(true);
    try {
      const res = await fetch(`${API_BASE}/portal/annotations/${subId}`, {
        method: 'POST',
        headers: { ...await getAuthHeaders(), 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ content: annotationText.trim() }),
      });
      if (!res.ok) throw new Error('Failed to save');
      setAnnotationText('');
      loadAnnotations();
      showToast('Annotation saved', 'success');
    } catch (e) {
      showToast(e.message || 'Failed to save', 'error');
    } finally {
      setSavingAnnotation(false);
    }
  }

  async function handleDeleteAnnotation(id) {
    try {
      const res = await fetch(`${API_BASE}/portal/annotations/${id}`, {
        method: 'DELETE',
        headers: await getAuthHeaders(),
        credentials: 'include',
      });
      if (res.ok) loadAnnotations();
    } catch (e) { console.warn("Failed to delete annotation:", e); showToast("Failed to delete annotation", "error"); }
  }

  if(!open) return null
  return (
    <dialog ref={dialogRef} className="modal-overlay" onClose={handleDialogClose} aria-label="Comparison details">
      <div className="modal-panel" onClick={e=>e.stopPropagation()} style={{ maxWidth: 900 }}>
        {loading ? (
          <div style={{ padding: 60, textAlign: 'center' }} role="status" aria-live="polite">
            <p>Loading submission texts...</p>
          </div>
        ) : (
        <>
        <div className="toolbar" style={{justifyContent:'space-between', alignItems:'flex-start'}}>
          <div>
            <div className="section-label" style={{marginBottom:10}}>Comparison details</div>
            <h3 className="section-title" style={{marginBottom:8}}>Similarity score: {(similarity * 100).toFixed(1)}%</h3>
            <p className="section-copy">
              Review the two submissions side by side. Highlighted passages indicate common text ({commonMatches.length} matches found).
            </p>
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
            <div style={{fontSize:13, color:'var(--text-soft)', marginBottom:8, lineHeight:1.6}}>
              <div><strong>Roll:</strong> {leftSubmission?.roll || "—"}</div>
              <div><strong>Name:</strong> {leftSubmission?.name || "—"}</div>
              <div><strong>File:</strong> {leftSubmission?.original_filename || (leftSubmission?.filename ? leftSubmission.filename.split("_").slice(3).join("_") : "—")}</div>
            </div>
            <HighlightedText text={leftSubmission?.text || leftSubmission?.snippet} matches={commonMatches} side="left" color="rgba(251,191,36,0.35)" />
          </div>
          <div className="surface" style={{padding:18, background:'rgba(255,255,255,.92)'}}>
            <div className="field-title" style={{marginBottom:4}}>Right submission</div>
            <div style={{fontSize:13, color:'var(--text-soft)', marginBottom:8, lineHeight:1.6}}>
              <div><strong>Roll:</strong> {rightSubmission?.roll || "—"}</div>
              <div><strong>Name:</strong> {rightSubmission?.name || "—"}</div>
              <div><strong>File:</strong> {rightSubmission?.original_filename || (rightSubmission?.filename ? rightSubmission.filename.split("_").slice(3).join("_") : "—")}</div>
            </div>
            <HighlightedText text={rightSubmission?.text || rightSubmission?.snippet} matches={commonMatches} side="right" color="rgba(251,191,36,0.35)" />
          </div>
        </div>

        <div style={{marginTop:18, padding:16, borderRadius:14, background:'rgba(248,251,255,.92)', border:'1px solid rgba(148,163,184,0.16)'}}>
          <div className="field-title" style={{marginBottom:8}}>Instructor annotations</div>
          {annotations.length > 0 ? (
            <div style={{marginBottom:12}}>
              {annotations.map(a => (
                <div key={a.id} style={{padding:'8px 12px', borderRadius:8, background:'var(--surface-muted)', marginBottom:6, fontSize:13, display:'flex', justifyContent:'space-between', alignItems:'flex-start'}}>
                  <div>{a.content}</div>
                  <button className="button-ghost" onClick={() => handleDeleteAnnotation(a.id)} style={{fontSize:11, padding:'2px 6px', color:'var(--danger)'}}>Remove</button>
                </div>
              ))}
            </div>
          ) : (
            <div style={{fontSize:13, color:'var(--text-soft)', marginBottom:10}}>No annotations yet.</div>
          )}
          <div style={{display:'flex', gap:8}}>
            <input
              value={annotationText}
              onChange={e => setAnnotationText(e.target.value)}
              placeholder="Add a note about this comparison..."
              style={{flex:1, padding:'6px 10px', borderRadius:8, border:'1px solid rgba(148,163,184,0.25)', fontSize:13}}
              onKeyDown={e => { if (e.key === 'Enter') handleAddAnnotation(); }}
            />
            <button className="button" onClick={handleAddAnnotation} disabled={!annotationText.trim() || savingAnnotation} style={{fontSize:12, padding:'6px 12px'}}>
              {savingAnnotation ? 'Saving...' : 'Add'}
            </button>
          </div>
        </div>
        </>
        )}
      </div>
    </dialog>
  )
}

MatrixViewer.propTypes = {
  open: PropTypes.bool.isRequired,
  onClose: PropTypes.func.isRequired,
  leftSubmission: PropTypes.object,
  rightSubmission: PropTypes.object,
  similarity: PropTypes.number,
  batchId: PropTypes.string,
  loading: PropTypes.bool,
};
