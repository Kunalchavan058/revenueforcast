import { TrainingControl } from "@/components/training-control";
import { ApiHealth } from "@/components/api-health";

/** Render local API health and honest saved-model/training onboarding. */
export default function Home(): React.JSX.Element {
  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-16">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">
          Local-first · Training and model reuse
        </p>
        <h1 className="text-4xl font-bold tracking-tight">RetailForecast AI</h1>
        <p className="text-lg text-muted-foreground">
          A foundation for understanding store sales.
        </p>
      </header>
      <ApiHealth />
      <TrainingControl />
      <section className="space-y-2" aria-labelledby="scope-heading">
        <h2 id="scope-heading" className="text-xl font-semibold">
          What is available
        </h2>
        <p className="text-muted-foreground">
          The local API supports validated imports, saved-model forecasts,
          exports, model versions and background training. This page provides
          training onboarding; forecast charts are a later step.
        </p>
        <p className="text-sm text-muted-foreground">
          The Rossmann dataset is historical. It is not a live sales feed.
        </p>
      </section>
    </main>
  );
}
