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