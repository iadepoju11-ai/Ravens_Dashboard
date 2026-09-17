interface Props {
  title: string;
}

// Route structure exists per CHECKLIST.md Phase 6 even though most pages
// aren't built yet — this says so plainly rather than showing a broken
// or fake-looking page.
export function NotYetBuiltPage({ title }: Props) {
  return (
    <div className="not-yet-built-page">
      <h1>{title}</h1>
      <p>This page isn't built yet — see CHECKLIST.md Phase 6.</p>
    </div>
  );
}
