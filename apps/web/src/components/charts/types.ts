import { z } from "zod";

export const MAX_CHART_POINTS = 1536;
export const salesPointsSchema = z
  .array(
    z.object({
      date: z.iso.date(),
      actual: z.number().finite().nonnegative().nullable(),
      predicted: z.number().finite().nonnegative().nullable(),
    }),
  )
  .max(MAX_CHART_POINTS)
  .refine(
    (points) =>
      new Set(points.map((point) => point.date)).size === points.length,
    "Each chart date must be unique.",
  );
export type SalesPoint = z.infer<typeof salesPointsSchema>[number];
