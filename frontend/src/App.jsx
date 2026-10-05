import { useState } from "react";
import "./App.css";
import Login from "./Login";
import DemandForecast from './DemandForecast';

function App() {
  const [loggedIn, setLoggedIn] = useState(false);

  if (!loggedIn) {
    return (
      <Login onLogin={() => setLoggedIn(true)} />
    );
  }

  return <DemandForecast />;
}

export default App;