import { app, BrowserWindow, Menu, shell } from "electron";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const DEFAULT_CONFIG = {
  appUrl: "http://127.0.0.1:3000",
  window: {
    width: 1440,
    height: 900,
    minWidth: 960,
    minHeight: 600,
  },
};

function loadConfig() {
  const configPath = path.join(__dirname, "config.json");
  let config = { ...DEFAULT_CONFIG, window: { ...DEFAULT_CONFIG.window } };

  if (fs.existsSync(configPath)) {
    try {
      const parsed = JSON.parse(fs.readFileSync(configPath, "utf8"));
      config = {
        ...config,
        ...parsed,
        window: { ...config.window, ...(parsed.window ?? {}) },
      };
    } catch (err) {
      console.warn("[ContextMap] Failed to read config.json:", err.message);
    }
  }

  if (process.env.CONTEXTMAP_APP_URL) {
    config.appUrl = process.env.CONTEXTMAP_APP_URL.replace(/\/$/, "");
  }

  return config;
}

function appOrigin(appUrl) {
  try {
    return new URL(appUrl).origin;
  } catch {
    return null;
  }
}

let mainWindow = null;

function createWindow() {
  const config = loadConfig();
  const allowedOrigin = appOrigin(config.appUrl);

  mainWindow = new BrowserWindow({
    width: config.window.width,
    height: config.window.height,
    minWidth: config.window.minWidth,
    minHeight: config.window.minHeight,
    show: false,
    title: "ContextMap",
    backgroundColor: "#282a36",
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, "preload.mjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  Menu.setApplicationMenu(null);

  mainWindow.once("ready-to-show", () => {
    mainWindow.show();
  });

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  mainWindow.webContents.on("will-navigate", (event, url) => {
    if (!allowedOrigin) return;
    try {
      if (new URL(url).origin !== allowedOrigin) {
        event.preventDefault();
        shell.openExternal(url);
      }
    } catch {
      event.preventDefault();
    }
  });

  mainWindow.webContents.on("did-fail-load", (_event, code, description, validatedURL) => {
    if (code === -3) return; // aborted navigation
    console.error(`[ContextMap] Failed to load ${validatedURL}: ${description} (${code})`);
  });

  mainWindow.loadURL(config.appUrl).catch((err) => {
    console.error("[ContextMap] loadURL error:", err.message);
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}

const gotLock = app.requestSingleInstanceLock();
if (!gotLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });

  app.whenReady().then(createWindow);

  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });

  app.on("window-all-closed", () => {
    if (process.platform !== "darwin") {
      app.quit();
    }
  });
}
