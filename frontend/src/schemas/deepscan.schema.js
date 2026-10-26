// DeepScan SSE + compile shapes (FastAPI, /deepscan).
// Mirrors the `is_final` payload emitted by backend_ai/deepscan/agno_router.py.
import { z } from 'zod';

// One figure the pipeline detected but couldn't extract (Phase I).
export const missingFigureSchema = z
  .object({
    n: z.number(),
    token: z.string().optional(),
    caption: z.string().optional().default(''),
  })
  .passthrough();

// Content-integrity report (Phase C).
export const integrityReportSchema = z
  .object({
    passed: z.boolean().optional(),
    severity: z.string().optional(),
    // field names as ContentIntegrityReport emits them
    word_retention_ratio: z.number().optional(),
    word_count_in: z.number().optional(),
    word_count_out: z.number().optional(),
    figure_count_in: z.number().optional(),
    figure_count_out: z.number().optional(),
    table_count_in: z.number().optional(),
    table_count_out: z.number().optional(),
    token_similarity: z.number().optional(),
    notes: z.array(z.string()).optional(),
  })
  .passthrough();

// The terminal SSE event of the pipeline stream.
export const pipelineFinalSchema = z
  .object({
    is_final: z.literal(true).optional(),
    latex: z.string().optional().default(''),
    job: z.string().nullable().optional(),
    formatted_file: z.string().nullable().optional(),
    assets: z.array(z.string()).optional().default([]),
    assets_base: z.string().optional(),
    figure_count: z.number().optional(),
    missing_figures: z.array(missingFigureSchema).optional().default([]),
    integrity: integrityReportSchema.nullable().optional(),
    content_integrity_passed: z.boolean().optional(),
  })
  .passthrough();

// A generic progress event (stage/log lines during the run).
export const pipelineEventSchema = z
  .object({
    stage: z.number().optional(),
    log: z.string().optional(),
    error: z.string().optional(),
  })
  .passthrough();
