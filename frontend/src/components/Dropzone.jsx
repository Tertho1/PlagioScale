import PropTypes from "prop-types";
import { useCallback, useState } from 'react'
import '../styles/portal.css'

export default function Dropzone({onFile}){
  const [hover, setHover] = useState(false)
  const onDrop = useCallback((e)=>{
    e.preventDefault(); setHover(false)
    const f = e.dataTransfer.files && e.dataTransfer.files[0]
    if(f && onFile) onFile(f)
  },[onFile])

  return (
    <div
      onDragOver={(e)=>{e.preventDefault(); setHover(true)}}
      onDragLeave={()=>setHover(false)}
      onDrop={onDrop}
      className={`file-zone ${hover ? 'is-hovered' : ''}`}
    >
      <div className="file-zone-row">
        <div>
          <strong>Drag and drop your file here</strong>
          <p>Or click the button below to choose a file from your computer.</p>
        </div>
        <label className="file-button">
          Choose file
          <input type="file" accept=".pdf,.docx,.txt,.md,.csv,.py,.java,.js,.ts" style={{display:'none'}} onChange={e=>onFile && onFile(e.target.files[0])} />
        </label>
      </div>
    </div>
  )
}

Dropzone.propTypes = {
  onFile: PropTypes.func.isRequired,
};
