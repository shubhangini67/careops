// components/ui/Spinner.tsx

export default function Spinner({ size = 24 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className="animate-spin"
      aria-label="Loading"
    >
      <circle
        cx="12" cy="12" r="10"
        stroke="rgba(230,137,42,0.2)"
        strokeWidth="2.5"
      />
      <path
        d="M12 2a10 10 0 0 1 10 10"
        stroke="#8b5cf6"
        strokeWidth="2.5"
        strokeLinecap="round"
      />
    </svg>
  );
}