/**
 * Protects a form in a dialog from being closed by accident. The form
 * reports whether it has unsaved changes (setDirty); closing then asks
 * "Discard your changes?" instead of silently throwing them away.
 *
 *   const guard = useDiscardGuard(() => setOpen(false));
 *   <Modal onClose={guard.requestClose} discard={guard.prompt}>
 *     <Form onDirtyChange={guard.setDirty} onCancel={guard.requestClose} ... />
 *   </Modal>
 *
 * After a successful save, call guard.close() (no question asked).
 */

import { useState } from "react";

export function useDiscardGuard(onClose: () => void) {
  const [dirty, setDirty] = useState(false);
  const [asking, setAsking] = useState(false);

  function close() {
    setDirty(false);
    setAsking(false);
    onClose();
  }

  function requestClose() {
    if (dirty) {
      setAsking(true);
    } else {
      close();
    }
  }

  return {
    setDirty,
    requestClose,
    close,
    // Passed to Modal: shows the question while it's being asked.
    prompt: asking ? { onDiscard: close, onKeep: () => setAsking(false) } : undefined,
  };
}
