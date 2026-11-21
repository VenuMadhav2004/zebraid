import { Button } from './Button.jsx'
import { Dialog } from './Dialog.jsx'

/** Confirmation for destructive actions. Mount it only while open (state resets on unmount). */
export function ConfirmDialog({ title, description, confirmLabel = 'Delete', tone = 'danger', busy, onConfirm, onClose, children }) {
  return (
    <Dialog
      open
      onClose={busy ? undefined : onClose}
      title={title}
      description={description}
      size="sm"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant={tone === 'danger' ? 'danger' : 'primary'} loading={busy} onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </>
      }
    >
      {children}
    </Dialog>
  )
}
