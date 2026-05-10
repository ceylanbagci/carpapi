import { useEffect } from "react";
import {
  animate,
  motion,
  useMotionValue,
  useReducedMotion,
  useTransform,
} from "framer-motion";

/**
 * Counts up to ``value`` once when it first becomes a real number.
 * Honours prefers-reduced-motion (renders the final number directly).
 */
export default function AnimatedNumber({
  value,
  duration = 1.4,
  delay = 0,
  format = (n) => Math.round(n).toLocaleString(),
  placeholder = "…",
}) {
  const reduce = useReducedMotion();
  const mv = useMotionValue(0);
  const display = useTransform(mv, (n) => format(n));

  useEffect(() => {
    if (typeof value !== "number") return;
    if (reduce) {
      mv.set(value);
      return;
    }
    const controls = animate(mv, value, {
      duration,
      delay,
      ease: [0.16, 1, 0.3, 1],
    });
    return () => controls.stop();
  }, [value, duration, delay, reduce, mv]);

  if (typeof value !== "number") {
    return <span>{placeholder}</span>;
  }
  return <motion.span>{display}</motion.span>;
}
