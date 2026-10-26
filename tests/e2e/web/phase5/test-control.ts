export {};
declare global {
  interface Window { __p5Render: (mode: string) => void; }
}
declare global {
  interface Window {
    __p5CreateStart: (kind?: string, mode?: string, fromReport?: boolean, operator?: boolean) => Promise<void>;
    __p5CreateCalls: () => { method: string; path: string; body?: string }[];
    __p5CreateUpdate: (kind: string, version?: string) => void;
    __p5CreateRelease: () => void;
    __p5CreateWriteMode: (mode: string) => void;
  }
}
