const COLORS = [
  'border-primary/30 bg-primary/10 text-primary',
  'border-sky-400/25 bg-sky-400/10 text-sky-300',
  'border-violet-400/25 bg-violet-400/10 text-violet-300',
  'border-emerald-400/25 bg-emerald-400/10 text-emerald-300',
];

export default function PluginAvatar({ id, name }) {
  const color = [...id].reduce((sum, char) => sum + char.charCodeAt(0), 0) % COLORS.length;
  const initials = name.trim().split(/\s+/).slice(0, 2).map(word => word[0]).join('');
  return <span aria-hidden="true" className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border text-sm font-semibold uppercase ${COLORS[color]}`}>
    {initials}
  </span>;
}
