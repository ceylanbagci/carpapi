import { motion, useReducedMotion } from "framer-motion";

/**
 * Side-view SVG sedan that drives in from the left of its container,
 * with wheels that keep spinning and headlights that pulse once it
 * arrives. Honours prefers-reduced-motion: drops in place with no
 * motion when the user has it set.
 */
export default function AnimatedCar({ width = 360 }) {
  const reduce = useReducedMotion();

  const wheel = reduce
    ? {}
    : {
        animate: { rotate: -360 },
        transition: { repeat: Infinity, duration: 0.8, ease: "linear" },
      };

  return (
    <motion.div
      className="d4-car-stage"
      initial={reduce ? false : { x: "-130%", opacity: 0 }}
      animate={reduce ? false : { x: 0, opacity: 1 }}
      transition={{
        type: "spring",
        stiffness: 55,
        damping: 14,
        mass: 1.1,
        delay: 0.25,
      }}
      style={{ width }}
    >
      <svg
        viewBox="0 0 360 140"
        width="100%"
        height="auto"
        role="img"
        aria-label="Car driving in"
      >
        {/* dust puff trailing the car */}
        {!reduce && (
          <motion.g
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.6, 0] }}
            transition={{
              duration: 1.4,
              delay: 0.4,
              ease: "easeOut",
            }}
          >
            <circle cx="20" cy="118" r="8" fill="#e8eaed" opacity="0.5" />
            <circle cx="38" cy="115" r="11" fill="#e8eaed" opacity="0.4" />
            <circle cx="58" cy="120" r="7" fill="#e8eaed" opacity="0.45" />
          </motion.g>
        )}

        {/* shadow under car */}
        <ellipse cx="180" cy="128" rx="140" ry="6" fill="rgba(0,0,0,0.35)" />

        {/* car body — lower section */}
        <path
          d="M50 110 Q50 92 70 90 L100 90 L120 70 Q130 60 150 58 L230 58 Q252 60 268 78 L300 90 L310 90 Q330 92 330 110 L330 118 L50 118 Z"
          fill="#3699ff"
          stroke="#0e2f5a"
          strokeWidth="1.5"
        />

        {/* upper greenhouse / windows */}
        <path
          d="M124 70 Q132 62 150 60 L228 60 Q248 62 263 78 L255 80 L130 80 Z"
          fill="#0f1115"
          opacity="0.85"
        />
        <line
          x1="190"
          y1="60"
          x2="190"
          y2="80"
          stroke="#0e2f5a"
          strokeWidth="1.4"
        />

        {/* headlight (front, right side of the car as drawn, pointing right) */}
        <motion.rect
          x="318"
          y="96"
          width="10"
          height="8"
          rx="2"
          fill="#fff7ae"
          stroke="#f5c518"
          strokeWidth="1"
          {...(reduce
            ? {}
            : {
                animate: { opacity: [0.5, 1, 0.85, 1] },
                transition: {
                  duration: 2,
                  delay: 1.2,
                  repeat: Infinity,
                  repeatType: "reverse",
                  ease: "easeInOut",
                },
              })}
        />
        {/* headlight beam */}
        {!reduce && (
          <motion.path
            d="M328 100 L356 88 L356 112 Z"
            fill="url(#beam)"
            initial={{ opacity: 0 }}
            animate={{ opacity: [0, 0.55, 0.35, 0.55] }}
            transition={{
              duration: 2.4,
              delay: 1.3,
              repeat: Infinity,
              repeatType: "reverse",
            }}
          />
        )}

        {/* tail light (back, left side) */}
        <rect
          x="52"
          y="98"
          width="6"
          height="6"
          rx="1.5"
          fill="#f1416c"
        />

        {/* door handle */}
        <rect
          x="160"
          y="96"
          width="22"
          height="2"
          rx="1"
          fill="#0e2f5a"
        />

        {/* wheels */}
        <g>
          <motion.g {...wheel} style={{ originX: "100px", originY: "118px" }}>
            <circle cx="100" cy="118" r="16" fill="#1a1a1a" />
            <circle cx="100" cy="118" r="9" fill="#3a3a3a" />
            <rect x="98" y="103" width="4" height="30" fill="#5a5a5a" />
            <rect
              x="85"
              y="116"
              width="30"
              height="4"
              fill="#5a5a5a"
              transform="rotate(60 100 118)"
            />
            <rect
              x="85"
              y="116"
              width="30"
              height="4"
              fill="#5a5a5a"
              transform="rotate(-60 100 118)"
            />
          </motion.g>
          <motion.g {...wheel} style={{ originX: "270px", originY: "118px" }}>
            <circle cx="270" cy="118" r="16" fill="#1a1a1a" />
            <circle cx="270" cy="118" r="9" fill="#3a3a3a" />
            <rect x="268" y="103" width="4" height="30" fill="#5a5a5a" />
            <rect
              x="255"
              y="116"
              width="30"
              height="4"
              fill="#5a5a5a"
              transform="rotate(60 270 118)"
            />
            <rect
              x="255"
              y="116"
              width="30"
              height="4"
              fill="#5a5a5a"
              transform="rotate(-60 270 118)"
            />
          </motion.g>
        </g>

        {/* gradient defs */}
        <defs>
          <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor="rgba(255,247,174,0.9)" />
            <stop offset="100%" stopColor="rgba(255,247,174,0)" />
          </linearGradient>
        </defs>
      </svg>
    </motion.div>
  );
}
