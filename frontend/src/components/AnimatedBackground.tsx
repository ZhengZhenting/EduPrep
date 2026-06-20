export function AnimatedBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 -z-10 overflow-hidden">
      {/* Warm red blob — top-left */}
      <div className="absolute -top-40 -left-40 h-[500px] w-[500px] rounded-full pulse-glow float-slow"
        style={{ background: "radial-gradient(circle, oklch(0.88 0.14 15 / 0.32), transparent 70%)" }} />
      {/* Golden amber blob — right */}
      <div className="absolute top-1/3 -right-32 h-[600px] w-[600px] rounded-full pulse-glow float-slow"
        style={{ background: "radial-gradient(circle, oklch(0.90 0.14 80 / 0.28), transparent 70%)", animationDelay: "2s" }} />
      {/* Warm yellow blob — bottom */}
      <div className="absolute bottom-0 left-1/4 h-[500px] w-[500px] rounded-full pulse-glow float-slow"
        style={{ background: "radial-gradient(circle, oklch(0.88 0.12 55 / 0.22), transparent 70%)", animationDelay: "4s" }} />
      {/* Subtle dot grid */}
      <div className="absolute inset-0 opacity-[0.04]"
        style={{ backgroundImage: "radial-gradient(rgba(0,0,0,0.8) 1px, transparent 1px)", backgroundSize: "32px 32px" }} />
    </div>
  );
}
