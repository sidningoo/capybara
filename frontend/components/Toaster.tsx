"use client";

import {
  createContext,
  ReactNode,
  useCallback,
  useContext,
  useState,
} from "react";

type ToastKind = "success" | "error" | "info";

interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

interface ToastCtx {
  push: (message: string, kind?: ToastKind) => void;
}

const Ctx = createContext<ToastCtx>({ push: () => {} });

export function useToast() {
  return useContext(Ctx);
}

let counter = 0;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const push = useCallback((message: string, kind: ToastKind = "info") => {
    const id = ++counter;
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 4000);
  }, []);

  const color: Record<ToastKind, string> = {
    success: "border-emerald-600 bg-emerald-950/90 text-emerald-100",
    error: "border-red-600 bg-red-950/90 text-red-100",
    info: "border-sky-600 bg-sky-950/90 text-sky-100",
  };

  return (
    <Ctx.Provider value={{ push }}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-80 flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto rounded-lg border px-4 py-2.5 text-sm shadow-xl ${color[t.kind]}`}
          >
            {t.message}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  );
}
