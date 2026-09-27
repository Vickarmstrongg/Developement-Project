import { useEffect, useState } from "react";

function App() {
  const [vendors, setVendors] = useState([]);

  useEffect(() => {
    fetch("http://127.0.0.1:8000/vendors")
      .then((res) => res.json())
      .then((data) => setVendors(data))
      .catch((err) => console.error("Error fetching vendors:", err));
  }, []);

  return (
    <div>
      <h1>Byte & Bite — Vendors (test)</h1>
      <ul>
        {vendors.map((v) => (
          <li key={v.vendor_id}>{v.name} — {v.address}</li>
        ))}
      </ul>
    </div>
  );
}

export default App;