import { useEffect } from "react";
import { Trash2 } from "lucide-react";
import "./DeleteEventPopup.css";

export default function DeleteEventPopup({
  event,
  loading = false,
  onConfirm,
  onCancel,
}) {
  const open = event !== null && event !== undefined;

  useEffect(() => {
    if (!open) return;

    function handleKeyDown(e) {
      if (e.key === "Escape" && !loading) {
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

  const dateText =
    event.start_date === event.end_date
      ? event.start_date
      : `${event.start_date} to ${event.end_date}`;

  return (
    <div
      className="delete-popup-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !loading) {
          onCancel?.();
        }
      }}
    >
      <div
        className="delete-popup"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="delete-popup-title"
        aria-describedby="delete-popup-message"
      >
        <div className="delete-popup-icon">
          <Trash2 size={26} />
        </div>

        <h2 id="delete-popup-title">Delete Event</h2>

        <p id="delete-popup-message">
          Are you sure you want to delete this event? This action cannot be
          undone.
        </p>

        <div className="delete-popup-event">
          <strong>{event.name}</strong>
          <span>{dateText}</span>
        </div>

        <div className="delete-popup-actions">
          <button
            type="button"
            className="delete-popup-cancel"
            onClick={onCancel}
            disabled={loading}
            autoFocus
          >
            Cancel
          </button>

          <button
            type="button"
            className="delete-popup-submit"
            onClick={onConfirm}
            disabled={loading}
          >
            {loading ? "Deleting..." : "Delete Event"}
          </button>
        </div>
      </div>
    </div>
  );
}