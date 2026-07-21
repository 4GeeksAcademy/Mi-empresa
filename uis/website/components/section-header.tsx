interface SectionHeaderProps {
  eyebrow: string;
  title: string;
  dark?: boolean;
}

export function SectionHeader({ eyebrow, title, dark = false }: SectionHeaderProps) {
  return (
    <header className="max-w-2xl">
      <p
        className="text-xs font-bold uppercase tracking-[0.2em]"
        style={{ color: dark ? "var(--brand-cyan)" : "var(--brand-orange)" }}
      >
        {eyebrow}
      </p>
      <h2
        className="mt-3 text-3xl font-extrabold sm:text-4xl"
        style={{ color: dark ? "#ffffff" : "var(--brand-blue-deep)" }}
      >
        {title}
      </h2>
    </header>
  );
}
