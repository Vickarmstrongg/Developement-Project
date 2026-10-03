import logo from "./assets/Logo.png";
function DemandForecast() {
    const forecastSummary = {
        expectedOrders: 1240,
        expectedCustomers: 1080,
        forecastPeriod: "7 Days",
    };

    const forecastData = [
        { day: "Mon", orders: 170, customers: 150, revenue: 7200 },
        { day: "Tue", orders: 180, customers: 160, revenue: 7800 },
        { day: "Wed", orders: 190, customers: 170, revenue: 8200 },
        { day: "Thu", orders: 200, customers: 180, revenue: 8900 },
        { day: "Fri", orders: 210, customers: 190, revenue: 9500 },
        { day: "Sat", orders: 220, customers: 200, revenue: 9800 },
        { day: "Sun", orders: 230, customers: 210, revenue: 10200 },
    ];
    // Temporary data - remove when connected to backend 
    
return (
    <div className="app-layout">

        <aside className="sidebar">
            <div className="brand">
                <span className="brand-name">Byte & Bite</span>

                <img
                    src={logo}
                    alt="Byte & Bite"
                    className="brand-logo"
                />
            </div>

            <div className="sidebar-section">
                <span className="sidebar-title">WORKSPACE</span>
                <nav>
                    <a href="#rush-hour-radar" className="sidebar-link">
                        <span>⌁</span>
                        Rush Hour Radar
                    </a>

                    <a href="#demand-forecast" className="sidebar-link active">
                        <span>◉</span>
                        Demand Forecast
                    </a>

                     <a href="#demand-forecast" className="sidebar-link active">
                        <span>◇</span>
                        Fair Comparison
                    </a>  
                </nav>
            </div>

            <div className="sidebar-section">
                <span className="sidebar-title">Reporting</span>
                <nav>
                    <a href="#reports" className="sidebar-link">
                        <span>↥</span>
                        Reports
                    </a>
                </nav>
            </div>

            <div className="user-profile">
                <div className="user-avatar">
                    U
                </div>

                <div className="user-details">
                    <strong>User Name</strong>
                    <span>Manager</span>
                </div>
            </div>
        </aside>

        <main className="main-content">

            <header className="topbar">
                <div className="breadcrumb">
                    Workspace / <strong>Demand Forecast</strong>
                </div>

                <div className="topbar-actions">
                    <select className="business-selector">
                        <option>All Businesses</option>
                        <option>Vendor 1</option>
                        <option> Vendor 2</option>
                    </select>
                </div>
            </header>
            
            <div className="page-content">
                <div className="page-heading">
                    <div>
                        <h1>Demand Forecast</h1>
                        <p>View expected demand for your business over the next seven days.</p>
                </div>
            </div>

            <section className="summary-grid">
                <div className="summary-card">
                    <span>EXPECTED ORDERS</span>
                    <strong>
                        {forecastSummary.expectedOrders}
                    </strong>
                    <small>
                        Next 7 days
                    </small>
                </div>

                 <div className="summary-card">
                    <span>EXPECTED CUSTOMERS</span>
                    <strong>
                        {forecastSummary.expectedCustomers}
                    </strong>
                    <small>
                        Next 7 days
                    </small>
                </div>

                 <div className="summary-card">
                    <span>FORECAST PERIOD</span>
                    <strong>
                        {forecastSummary.forecastPeriod}
                    </strong>
                    <small>
                        Weekly forecast
                    </small>
                </div>
            </section>





        </main>
