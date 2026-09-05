import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AIResearchTab from "./AIResearchTab";
import NavigationChrome from "./NavigationChrome";
import "./styles.css";
import "./phase-pages.css";
import "./technical-analysis.css";
import "./ai-tab.css";
import "./navigation.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <NavigationChrome />
    <AIResearchTab />
  </React.StrictMode>,
);
