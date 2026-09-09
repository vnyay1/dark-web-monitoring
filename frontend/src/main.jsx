import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { FournisseurSession } from "./api/session";
import "./theme/tokens.css";
import "./theme/base.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <FournisseurSession>
        <App />
      </FournisseurSession>
    </BrowserRouter>
  </React.StrictMode>,
);
