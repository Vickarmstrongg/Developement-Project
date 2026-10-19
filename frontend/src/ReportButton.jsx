import { useState } from "react";
import { Printer } from "lucide-react";
import { apiFetch } from "./api";
import "./print.css";

function formatNow() {
    return new Date().toLocaleString("en-ZA", {
        dateStyle: "long",
        timeStyle: "short",
    });
}

function ReportButton({
    title,
    subtitle,
    reportType,
    vendorId,
    periodStart,
    periodEnd,
    onPrintStart,
    onPrintEnd,
}) {
    const [generated, setGenerated] = useState(formatNow());
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState("");

    async function logExport() {
        const response = await apiFetch("/api/reports/exports", {
            method: "POST",
            body: JSON.stringify({
                report_type: reportType,
                vendor_id: vendorId ? Number(vendorId) : null,
                period_start: periodStart || null,
                period_end: periodEnd || null,
            }),
        });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(
                typeof data.detail === "string"
                    ? data.detail
                    : "The export could not be recorded."
            );
        }
    }

    async function handlePrint() {
        setError("");
        setBusy(true);

        try {
            // record who exported what before anything is printed
            if (reportType) await logExport();
        } catch (err) {
            setError(`Export not generated: ${err.message}`);
            setBusy(false);
            return;
        }

        // open "View daily figures" so the table appears in the report
        document.querySelectorAll("details").forEach((d) => {
            d.open = true;
        });

        setGenerated(formatNow());

        // name the PDF properly instead of "frontend"
        const originalTitle = document.title;
        document.title = `Byte & Bite - ${title}`;

        if (onPrintStart) onPrintStart();

        function cleanup() {
            document.title = originalTitle;
            if (onPrintEnd) onPrintEnd();
            window.removeEventListener("afterprint", cleanup);
        }
        window.addEventListener("afterprint", cleanup);

        // give the page a moment to redraw before printing
        setTimeout(() => {
            window.print();
            setBusy(false);
        }, 400);
    }

    return (
        <>
            <button
                type="button"
                className="report-button"
                onClick={handlePrint}
                disabled={busy}
            >
                <Printer size={14} />
                {busy ? "Preparing..." : "Export report"}
            </button>

            {error && (
                <span
                    role="alert"
                    className="report-button-error"
                    style={{ color: "#b42318", fontSize: 11 }}
                >
                    {error}
                </span>
            )}

            {/* only visible when printing */}
            <div className="report-header">
                <h1>Byte &amp; Bite – {title}</h1>
                {subtitle && <p>{subtitle}</p>}
                <p>Generated {generated}</p>
            </div>
        </>
    );
}

export default ReportButton;