import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AIResearchTab from "./AIResearchTab";
import "./styles.css";
import "./phase-pages.css";
import "./technical-analysis.css";
import "./ai-tab.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <AIResearchTab />
  </React.StrictMode>,
);
