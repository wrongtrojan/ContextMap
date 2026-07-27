export {};

declare global {
  interface Window {
    contextmapDesktop?: {
      isElectron: boolean;
      platform: NodeJS.Platform;
    };
  }
}
