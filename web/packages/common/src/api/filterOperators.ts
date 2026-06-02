// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * Mongo-style comparison operators accepted by NeMo Platform's unified filter
 * syntax (e.g. `{ name: { $like: '%foo%' } }`, `{ created_at: { $gte, $lte } }`).
 *
 * The OpenAPI-generated SDK types model filter fields as bare scalars
 * (`name?: string`) and do not expose the operator-object form. Use
 * {@link WithFilterOperators} to widen a generated filter shape so call sites
 * can build operator filters without `as unknown as` casts.
 */
export interface FilterOperators<V> {
  $eq?: V;
  $ne?: V;
  $in?: readonly V[];
  $nin?: readonly V[];
  $gt?: V;
  $gte?: V;
  $lt?: V;
  $lte?: V;
  /** Substring match (e.g. `%foo%`). String-typed regardless of `V`. */
  $like?: string;
}

/**
 * Widens each field of `F` so it accepts either its original scalar value or
 * a {@link FilterOperators} object. Intended for API call sites that need
 * operator-object filters; coerce back to the generated filter type once at
 * the SDK boundary.
 *
 * @example
 * type ModelFilterInput = WithFilterOperators<ModelEntityFilter>;
 * const filter: ModelFilterInput = { name: { $like: '%foo%' } };
 */
export type WithFilterOperators<F> = {
  [K in keyof F]?: F[K] | FilterOperators<NonNullable<F[K]>>;
};

/**
 * Build a typed operator-filter and coerce it to the generated SDK filter type
 * in one step. Centralizes the unavoidable cast at the SDK boundary so call
 * sites can be written with full type-checking on operator objects.
 *
 * @example
 * filter: withOperators<FilesetFilter>({ name: { $like: `%${search}%` } })
 */
export const withOperators = <F>(filter: WithFilterOperators<F>): F => filter as F;
