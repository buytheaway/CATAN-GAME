export type RulesetCompatibility = {
  status: "compatible" | "compatibility_required";
  ruleset_id: string | null;
  current_ruleset_id: string;
};

export function needsCompatibility(value: { ruleset_compatibility?: RulesetCompatibility } | null) {
  return value?.ruleset_compatibility?.status === "compatibility_required";
}
