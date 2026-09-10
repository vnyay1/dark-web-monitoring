// Styles de base EN PREMIER : ils doivent preceder les feuilles propres aux
// composants et aux pages, qui les surchargent. Importes apres App, ils se
// retrouvaient en fin de bundle et ecrasaient ces surcharges a specificite
// egale - c'est ce qui rendait le bouton Menu visible, et inoperant, sur
// grand ecran.
import "./theme/tokens.css";
import "./theme/base.css";

import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import { FournisseurSession } from "./api/session";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <FournisseurSession>
        <App />
      </FournisseurSession>
    </BrowserRouter>
  </React.StrictMode>,
);
