export type ToastInput = {
  title?: string;
  description?: string;
  variant?: "default" | "destructive";
};

export function toast(t: ToastInput) {
  // Minimal no-dependency toast:
  // logs in console; optional alert for destructive
  if (typeof window !== "undefined") {
    const msg = [t.title, t.description].filter(Boolean).join(" — ");
    if (t.variant === "destructive") {
      alert(msg || "Something went wrong");
    } else {
      console.log("TOAST:", msg);
    }
  }
}
