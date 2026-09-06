import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AIResearchTab from "./AIResearchTab";
import NewsResearchTab from "./NewsResearchTab";
import NavigationChrome from "./NavigationChrome";
import "./styles.css";
import "./phase-pages.css";
import "./technical-analysis.css";
import "./ai-tab.css";
import "./news-tab.css";
import "./news-research.css";
import "./navigation.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <NavigationChrome />
    <AIResearchTab />
    <NewsResearchTab />
  </React.StrictMode>,
);
