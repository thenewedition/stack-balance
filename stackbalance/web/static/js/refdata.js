"use strict";

/** Shared reference data (accounts, groups, categories) with name lookups.
 *  Views call load() on entry; anything that mutates these calls invalidate(). */

import { api } from "./api.js";

const state = { accounts: [], groups: [], categories: [], loaded: false };

export async function load(force = false) {
  if (state.loaded && !force) return state;
  const [accounts, groups, categories] = await Promise.all([
    api.get("/accounts?include_inactive=true"),
    api.get("/category-groups"),
    api.get("/categories?include_archived=true"),
  ]);
  state.accounts = accounts;
  state.groups = groups;
  state.categories = categories;
  state.loaded = true;
  return state;
}

export const invalidate = () => { state.loaded = false; };

export const accountName = (id) =>
  state.accounts.find(a => a.id === id)?.name ?? "?";

export const categoryName = (id) =>
  id == null ? "—" : (state.categories.find(c => c.id === id)?.name ?? "?");

export const groupName = (id) =>
  state.groups.find(g => g.id === id)?.name ?? "?";

export const activeAccounts = () => state.accounts.filter(a => a.is_active);

export const spendingCategories = () =>
  state.categories.filter(c => !c.is_income && !c.is_archived);

export const allCategoryOptions = () => {
  const byGroup = new Map(state.groups.map(g => [g.id, g.name]));
  return state.categories
    .filter(c => !c.is_archived)
    .map(c => ({ value: c.id, label: `${byGroup.get(c.group_id) ?? "?"}: ${c.name}` }));
};

export const data = state;
