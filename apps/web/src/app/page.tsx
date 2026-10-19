import { ApiHealth } from "@/components/api-health";

/** Render the scaffold's scope and actual local API connection state. */
export default function Home(): React.JSX.Element {
  return (
    <main className="mx-auto max-w-3xl space-y-8 px-6 py-16">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-widest text-primary">
          Local-first · Phase 3
        </p>
        <h1 className="text-4xl font-bold tracking-tight">RetailForecast AI</h1>
        <p className="text-lg text-muted-foreground">
          A foundation for understanding store sales.
        </p>
      </header>
      <ApiHealth />
      <section className="space-y-2" aria-labelledby="scope-heading">
        <h2 id="scope-heading" className="text-xl font-semibold">
          What is available
        </h2>
        <p className="text-muted-foreground">
          This starter checks the connection between the web app and local API.
          Imports, forecasting, training, model history, and charts are not
          implemented.
        </p>
        <p className="text-sm text-muted-foreground">
          The Rossmann dataset is historical. It is not a live sales feed.
        </p>
      </section>
    </main>
  );
}
