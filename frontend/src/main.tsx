import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import NavigationChrome from "./NavigationChrome";
import "./styles.css";
import "./phase-pages.css";
import "./technical-analysis.css";
import "./ai-tab.css";
import "./news-tab.css";
import "./news-research.css";
import "./research-reports-tab.css";
import "./research-history.css";
import "./research-history-tab.css";
import "./alerts.css";
import "./navigation.css";
import "./settings.css";
import "./market-data-health.css";
import "./display-interface.css";
import "./billing.css";\nimport "./phase9.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <NavigationChrome />
  </React.StrictMode>,
);
