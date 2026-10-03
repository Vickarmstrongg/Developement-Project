function DemandForecast() {
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
        </div>
    );
}

export default DemandForecast;