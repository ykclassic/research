import React,{useEffect,useState} from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import NavigationChrome from "./NavigationChrome";
import Phase10Page from "./Phase10Page";
import { getCurrentUser, User } from "./api";
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
import "./billing.css";
import "./phase9.css";
import "./phase10.css";

function Phase10Route(){
 const[user,setUser]=useState<User|null>(null); const[checking,setChecking]=useState(true);
 useEffect(()=>{let active=true;getCurrentUser().then(next=>{if(active)setUser(next)}).catch(()=>{if(active)setUser(null)}).finally(()=>{if(active)setChecking(false)});return()=>{active=false}},[]);
 if(checking)return <div className="auth-loading">Checking session…</div>;
 return user?<Phase10Page user={user} onLogout={()=>setUser(null)}/>:<App/>;
}
function Root(){const[phase10,setPhase10]=useState(()=>window.location.pathname==="/intelligence/optimization");useEffect(()=>{const sync=()=>setPhase10(window.location.pathname==="/intelligence/optimization");window.addEventListener("popstate",sync);return()=>window.removeEventListener("popstate",sync)},[]);return <React.StrictMode>{phase10?<Phase10Route/>:<App/>}<NavigationChrome/></React.StrictMode>}
ReactDOM.createRoot(document.getElementById("root")!).render(<Root/>);
