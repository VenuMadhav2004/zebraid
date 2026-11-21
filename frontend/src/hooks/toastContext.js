import { createContext, useContext } from 'react'

export const ToastContext = createContext(null)

/** toast({title, description?, tone?: 'success'|'danger'|'info'}) */
export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}
