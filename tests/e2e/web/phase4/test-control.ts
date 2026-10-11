// Only the component test iframe exposes these memory observations.
declare global {
  interface Window {
    __p4: {
      calls: { method: string; path: string; body?: string }[];
      render: (mode: string) => void;
      release: () => void;
      revoke: () => void;
    };
  }
}
export {};
