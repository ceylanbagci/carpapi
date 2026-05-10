export default function Footer() {
  const year = new Date().getFullYear();
  return (
    <footer className="d4-footer">
      <span>© {year} CarPapi · Demo4-inspired admin</span>
      <span>
        <a
          href="https://github.com/ceylanbagci/carpapi"
          target="_blank"
          rel="noreferrer"
          className="text-muted"
        >
          GitHub
        </a>
      </span>
    </footer>
  );
}
