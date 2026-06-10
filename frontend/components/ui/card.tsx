import { cn } from "@/lib/utils"

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "card-gradient card-shadow rounded-2xl border border-brand-border/60",
        "transition-all duration-200",
        className
      )}
      {...props}
    />
  )
}

export function CardHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "flex items-center justify-between px-5 py-4 border-b border-brand-border/40",
        className
      )}
      {...props}
    />
  )
}

export function CardTitle({ className, ...props }: React.HTMLAttributes<HTMLHeadingElement>) {
  return (
    <h3
      className={cn(
        "text-sm font-semibold text-brand-text-bright tracking-tight",
        className
      )}
      {...props}
    />
  )
}

export function CardContent({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("p-5", className)} {...props} />
}

export function Badge({
  className,
  variant = "default",
  ...props
}: React.HTMLAttributes<HTMLSpanElement> & { variant?: "default" | "success" | "danger" | "warning" | "info" | "neutral" }) {
  const variants = {
    default: "bg-brand-border/50 text-brand-text",
    success: "bg-brand-green/10 text-brand-green",
    danger: "bg-brand-red/10 text-brand-red",
    warning: "bg-brand-amber/10 text-brand-amber",
    info: "bg-brand-accent/10 text-brand-accent",
    neutral: "bg-brand-card text-brand-text/60 border border-brand-border",
  }
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-lg",
        variants[variant],
        className
      )}
      {...props}
    />
  )
}

export function Separator({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={cn("h-px bg-brand-border/40", className)} {...props} />
}
