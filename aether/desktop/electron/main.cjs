const { app, BrowserWindow, shell } = require("electron");
const path = require("path");

function createWindow() {
  const win = new BrowserWindow({
    width: 1380,
    height: 900,
    minWidth: 760,
    minHeight: 620,
    backgroundColor: "#212121",
    title: "AETHER",
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true
    }
  });

  const appOrigin = app.isPackaged ? null : "http://127.0.0.1:5173";

  if (!app.isPackaged) {
    win.loadURL(appOrigin);
  } else {
    win.loadFile(path.join(__dirname, "../dist/index.html"));
  }

  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });

  // The window has no address bar or back button, so if anything ever navigates it away
  // from the app's own page (e.g. a link the renderer didn't intercept), the user would be
  // stuck looking at a raw server response with no way back. Anything outside the app's
  // own origin opens in the system browser instead, and in-app navigation stays put.
  win.webContents.on("will-navigate", (event, url) => {
    const isAppPage = appOrigin
      ? url.startsWith(appOrigin)
      : url.startsWith("file://") && url.includes(path.join(__dirname, "../dist"));
    if (isAppPage) return;
    event.preventDefault();
    shell.openExternal(url);
  });
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
