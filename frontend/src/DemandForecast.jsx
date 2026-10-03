function DemandForecast() {
    const forecastSummary = {
        expectedOrders: 1240,
        expectedCustomers: 1080,
        forecastPeriod: "7 Days",
    }; 

const forecastData = [
    { day: "Mon", orders: 170, customers: 150 },
    { day: "Tue", orders: 180, customers: 160 },
    { day: "Wed", orders: 190, customers: 170 },
    { day: "Thu", orders: 200, customers: 180 },
    { day: "Fri", orders: 210, customers: 190 },
    { day: "Sat", orders: 220, customers: 200 },
    { day: "Sun", orders: 230, customers: 210 }
];

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
                    <strong>{forecastSummary.expectedOrders}</strong>
                    <small>Next 7 days</small>
                </div>

                <div className="summary-card">
                    <span>Expected Customers</span>
                    <strong>{forecastSummary.expectedCustomers}</strong>
                    <small>Next 7 days</small>
                </div>
                
                <div className="summary-card">
                    <span>Forecast Period</span>
                    <strong>{forecastSummary.forecastPeriod}</strong>
                    <small>Weekly Forecast</small>
                </div>
            </section>

            <section className="forecast-card">
                <div className="forecast-card-header">
                    <div>
                        <h2>Weekly Demand Forecast</h2>
                        <p>Expected orders and customers for the next seven days.</p>
                    </div>
                </div>

                <div className="forecast-chart">
                    {forecastData.map((item) => (
                        <div className="forecast-day" key={item.day}>
                            <div className="bar-area">
                                <div
                                    className="forecast-bar"
                                    style={{ height: `${item.orders / 2}px` }}
                                ></div>
                            </div>

                            <strong>{item.orders}</strong>
                            <span>{item.day}</span>
                        </div>
                    ))}
                </div>
            </section>
        </div>
    );
}

export default DemandForecast;