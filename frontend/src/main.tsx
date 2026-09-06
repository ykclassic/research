import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import AIResearchTab from "./AIResearchTab";
import NewsResearchTab from "./NewsResearchTab";
import ResearchReportsTab from "./ResearchReportsTab";
import ResearchHistoryTab from "./ResearchHistoryTab";
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
import "./navigation.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
    <NavigationChrome />
    <AIResearchTab />
    <NewsResearchTab />
    <ResearchReportsTab />
    <ResearchHistoryTab />
  </React.StrictMode>,
);
