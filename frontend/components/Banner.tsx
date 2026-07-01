// Persistent "synthetic data only" banner — execute-plan §11: the demo must
// visibly use synthetic data only, never anything resembling real PHI.

export function Banner() {
  return (
    <div className="w-full bg-amber-100 text-amber-900 text-center text-xs font-medium py-1.5 px-4 border-b border-amber-200">
      Synthetic data only — this is a demo. Do not enter real patient information.
    </div>
  );
}
