import { contextBridge } from "electron";

contextBridge.exposeInMainWorld("contextmapDesktop", {
  isElectron: true,
  platform: process.platform,
});

window.addEventListener("DOMContentLoaded", () => {
  document.body.classList.add("electron-shell");
  document.documentElement.classList.add("electron-shell");
});
