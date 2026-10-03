function DemandForecast() {
    const forcastSummary = {
        expectedOrders: 1240,
        expectedCustomers: 1080,
        forecastPeriod: "7 Days",
    }; 
// Above here is the temporary data, when joined with backend REMOVE THIS

    return (
        <div className="demand-forecast">
            <header className="forecast-header">
                <div>
                    <h1>Demand Forecast</h1>
                    <p>
                        View expected demand for your business over the next seven days.
                    </p>
                </div>

                <div className="business-selector">
                    <label htmlFor="business">Business</label>
                    <select id="business">
                        <option>All Businesses</option>
                        <option>Vendor 1</option>
                        <option>Vendor 2</option>
                    </select>
                </div>
            </header>

            <section className="summary-grid">
                <div className="summary-card">
                    <span>Expected Orders</span>
                    <strong>{forcastSummary.expectedOrders}</strong>
                    <small>Next 7 days</small>
                </div>

                <div className="summary-card">
                    <span>Expected Customers</span>
                    <strong>{forcastSummary.expectedCustomers}</strong>
                    <small>Next 7 days</small>
                </div>
                <div className="summary-card">
                    <span>Forecast Period</span>
                    <strong>{forcastSummary.forecastPeriod}</strong>
                    <small>Weekly Forecast</small>
                </div>
            </section>
        </div>
    );
}

export default DemandForecast;