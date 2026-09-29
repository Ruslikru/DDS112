import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { App } from "./App";
import "./style.css";
import "./workstation.css";
import "./arm.css";
import "./classroom.css";
import "./arm-refinements.css";
import { initializeDiagnostics, reportDiagnostic } from './diagnostics';
initializeDiagnostics();
class ErrorBoundary extends React.Component<React.PropsWithChildren,{failed:boolean}>{
  state={failed:false};
  static getDerivedStateFromError(){return {failed:true};}
  componentDidCatch(error:Error,info:React.ErrorInfo){try{(window as any).pywebview?.api?.report_ui_error?.(error.message,info.componentStack||error.stack||'')?.catch?.(()=>{});}catch{}reportDiagnostic('react_error',error.message,{stack:(info.componentStack||error.stack||'').slice(0,4000)});}
  render(){return this.state.failed?<div className="page"><h1>Ошибка интерфейса</h1><p>Диагностика сохранена локально. Перезагрузите экран; серверные данные сохраняются.</p><button onClick={()=>location.reload()}>Перезагрузить</button></div>:this.props.children;}
}
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary><BrowserRouter>
    <App />
  </BrowserRouter></ErrorBoundary>,
);
