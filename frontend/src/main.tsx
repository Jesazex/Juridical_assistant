import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import "@fontsource/manrope/cyrillic-400.css";
import "@fontsource/manrope/cyrillic-500.css";
import "@fontsource/manrope/cyrillic-600.css";
import "@fontsource/manrope/cyrillic-700.css";
import "@fontsource/manrope/latin-400.css";
import "@fontsource/manrope/latin-500.css";
import "@fontsource/manrope/latin-600.css";
import "@fontsource/manrope/latin-700.css";
import "@fontsource/literata/cyrillic-400.css";
import "@fontsource/literata/cyrillic-600.css";
import "@fontsource/literata/latin-400.css";
import "@fontsource/literata/latin-600.css";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Корневой элемент не найден");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
