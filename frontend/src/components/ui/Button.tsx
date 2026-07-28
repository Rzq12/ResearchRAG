import { forwardRef, type ButtonHTMLAttributes } from "react";
import { CircleNotch } from "@phosphor-icons/react";

import { cn } from "@/lib/utils";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg" | "icon";

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary: "bg-accent text-zinc-950 hover:bg-accent-soft focus-visible:ring-accent/50",
  secondary: "bg-white/[0.06] text-zinc-100 hover:bg-white/[0.10] focus-visible:ring-zinc-500/40",
  ghost: "bg-transparent text-zinc-400 hover:bg-white/[0.05] hover:text-zinc-100 focus-visible:ring-zinc-600/40",
  danger: "bg-rose-500/90 text-white hover:bg-rose-500 focus-visible:ring-rose-400/40",
  outline: "border border-white/[0.08] bg-transparent text-zinc-200 hover:bg-white/[0.04] focus-visible:ring-zinc-500/40",
};

const SIZES: Record<Size, string> = {
  sm: "h-8 px-3 text-xs gap-1.5",
  md: "h-10 px-4 text-sm gap-2",
  lg: "h-11 px-5 text-[15px] gap-2",
  icon: "h-9 w-9 p-0",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  (
    { className, variant = "secondary", size = "md", loading, fullWidth, children, disabled, ...props },
    ref,
  ) => (
    <button
      ref={ref}
      disabled={disabled || loading}
      className={cn(
        "inline-flex select-none items-center justify-center rounded-xl font-medium tracking-tight",
        "transition-all duration-200 ease-smooth active:scale-[0.98]",
        "focus:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-offset-zinc-950",
        "disabled:pointer-events-none disabled:opacity-50",
        VARIANTS[variant],
        SIZES[size],
        fullWidth && "w-full",
        className,
      )}
      {...props}
    >
      {loading && <CircleNotch className="h-4 w-4 animate-spin" />}
      {children}
    </button>
  ),
);
Button.displayName = "Button";
