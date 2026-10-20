import Link from "next/link";
import { notFound } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { EmptyState } from "@/components/foundation/empty-state";
import { PageHeader } from "@/components/foundation/page-header";
import { navigation } from "@/lib/navigation";

export const dynamicParams = false;

/** Only explicitly planned navigation destinations are statically published. */
export function generateStaticParams(): { workspace: string }[] {
  return navigation
    .filter((item) => item.emptyTitle)
    .map((item) => ({ workspace: item.href.slice(1) }));
}

/** Honest destination shells reserve feature workflows for subsequent phases. */
export default async function WorkspacePage({
  params,
}: {
  params: Promise<{ workspace: string }>;
}): Promise<React.JSX.Element> {
  const { workspace } = await params;
  const page = navigation.find(
    (item) => item.href === `/${workspace}` && item.emptyTitle,
  );
  if (!page) notFound();
  return (
    <>
      <PageHeader title={page.label} description={page.description} />
      <Card>
        <div className="flex items-center justify-between gap-4 border-b border-border px-6 py-4">
          <h2 className="text-sm font-semibold">{page.label} workspace</h2>
          <span className="text-xs text-muted-foreground">
            Browser workflow planned
          </span>
        </div>
        <EmptyState
          title={page.emptyTitle}
          description={page.emptyDescription}
          icon={page.icon}
          action={
            <Button variant="outline" asChild>
              <Link href="/">Back to overview</Link>
            </Button>
          }
        />
      </Card>
    </>
  );
}
