/**
 * <CarThumb /> — small car profile picture.
 *
 * Renders, in priority order:
 *   1. <img> for image_url   (the 240×160 JPEG on CloudFront)
 *   2. <img> for image_svg_url (the silhouette traced by potrace)
 *   3. The bi-car-front-fill bootstrap-icons glyph (final fallback)
 *
 * `onError` chains down the priority list at runtime so a 404 on
 * the JPEG transparently falls through to the SVG, then to the icon.
 *
 * Sizing is set via `width`/`height` props — the underlying asset is
 * 240×160 so anything smaller scales cleanly without artifacts.
 */
export default function CarThumb({
  imageUrl,
  imageSvgUrl,
  alt = "",
  width = 96,
  height = 64,
  rounded = 10,
  style = {},
}) {
  const wrap = {
    width,
    height,
    borderRadius: rounded,
    overflow: "hidden",
    background: "linear-gradient(135deg, #f3f4f6, #e5e7eb)",
    flexShrink: 0,
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    color: "#9aa3b2",
    fontSize: Math.max(18, Math.min(width, height) * 0.45),
    ...style,
  };
  const img = {
    width: "100%",
    height: "100%",
    objectFit: "cover",
    display: "block",
  };
  // No source at all → just the icon over the gradient.
  if (!imageUrl && !imageSvgUrl) {
    return (
      <span style={wrap} aria-hidden="true">
        <i className="bi bi-car-front-fill"></i>
      </span>
    );
  }
  // JPEG first; SVG fallback; icon last.
  const primary = imageUrl || imageSvgUrl;
  const fallback = imageUrl ? imageSvgUrl : null;
  return (
    <span style={wrap}>
      <img
        src={primary}
        alt={alt}
        loading="lazy"
        decoding="async"
        style={img}
        onError={(e) => {
          const el = e.currentTarget;
          if (fallback && el.dataset.fallbackTried !== "1") {
            el.dataset.fallbackTried = "1";
            el.src = fallback;
            return;
          }
          // Last resort — hide the <img> so the gradient + icon parent show through.
          el.style.display = "none";
        }}
      />
    </span>
  );
}
