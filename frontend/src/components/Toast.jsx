import { useCallback, useEffect, useState } from 'react'
import '../styles/portal.css'

let toastId = 0
const listeners = new Set()

export function showToast(message, type = 'success', duration = 4000) {
  const id = ++toastId
  for (const fn of listeners) {
    fn({ id, message, type, duration })
  }
}

export default function ToastContainer() {
  const [toasts, setToasts] = useState([])

  useEffect(() => {
    const handler = (toast) => {
      setToasts((prev) => [...prev, toast])
    }
    listeners.add(handler)
    return () => listeners.delete(handler)
  }, [])

  const remove = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <div className="toast-container">
      {toasts.map((t) => (
        <ToastItem key={t.id} {...t} onDone={remove} />
      ))}
    </div>
  )
}

function ToastItem({ id, message, type, duration, onDone }) {
  useEffect(() => {
    const timer = setTimeout(() => onDone(id), duration)
    return () => clearTimeout(timer)
  }, [id, duration, onDone])

  return (
    <div className={`toast toast-${type}`} onClick={() => onDone(id)} role="alert">
      {message}
    </div>
  )
}
