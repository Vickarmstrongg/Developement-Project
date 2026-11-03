import { useEffect } from "react";
import "./ConfirmPopup.css";

export default function ConfirmPopup({
  open,
  title = "Confirm Action",
  message = "Are you sure you want to continue?",
  confirmText = "Confirm",
  variant = "danger",
  onConfirm,
  onCancel,
  loading = false,
}) {
  useEffect(() => {
    if (!open) return;

    function handleKeyDown(event) {
      if (event.key === "Escape" && !loading) {
        onCancel?.();
      }
    }

    document.addEventListener("keydown", handleKeyDown);

    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", handleKeyDown);
      document.body.style.overflow = previousOverflow;
    };
  }, [open, loading, onCancel]);

  if (!open) return null;

  const isDanger = variant === "danger";

  return (
    <div
      className="confirm-popup-overlay"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !loading) {
          onCancel?.();
        }
      }}
    >
      <div
        className="confirm-popup"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-popup-title"
        aria-describedby="confirm-popup-message"
      >
        <div
          className={`confirm-popup-icon ${
            isDanger ? "danger" : "success"
          }`}
        >
          {isDanger ? "!" : "✓"}
        </div>

        <h2 id="confirm-popup-title">{title}</h2>

        <p id="confirm-popup-message">{message}</p>

        <div className="confirm-popup-actions">
          <button
            type="button"
            className="confirm-popup-cancel"
            onClick={onCancel}
            disabled={loading}
          >
            Cancel
          </button>

          <button
            type="button"
            className={`confirm-popup-submit ${
              isDanger ? "danger" : "success"
            }`}
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "Processing..." : confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
