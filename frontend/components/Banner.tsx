// Persistent "synthetic data only" banner — execute-plan §11: the demo must
// visibly use synthetic data only, never anything resembling real PHI.

export function Banner() {
  return (
    <div className="w-full border-b border-ember-300 bg-ember-500 px-4 py-1.5 text-center font-sans text-xs font-medium tracking-wide text-white">
      Synthetic data only — this is a demo. Do not enter real patient information.
    </div>
  );
}
