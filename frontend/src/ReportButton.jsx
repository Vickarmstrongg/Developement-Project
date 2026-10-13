import { useState } from "react";
import { Printer } from "lucide-react";
import "./print.css";

function formatNow() {
    return new Date().toLocaleString("en-ZA", {
        dateStyle: "long",
        timeStyle: "short",
    });
}

function ReportButton({ title, subtitle, onPrintStart, onPrintEnd }) {
    const [generated, setGenerated] = useState(formatNow());

    function handlePrint() {
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
        setTimeout(() => window.print(), 400);
    }

    return (
        <>
            <button
                type="button"
                className="report-button"
                onClick={handlePrint}
            >
                <Printer size={14} />
                Export report
            </button>

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