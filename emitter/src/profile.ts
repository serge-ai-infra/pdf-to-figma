/**
 * A profile is data the user supplies — never a default this tool ships with.
 * Architecture rule 3: "Profiles are data, supplied by the user. Shipped
 * profiles are examples only." `example.profile.json` in this directory is
 * documentation, never read unless a caller explicitly passes it.
 */

export interface ProfileEntry {
  name?: string;
  component?: boolean;
  liveText?: boolean;
}

export interface Profile {
  candidates?: Record<string, ProfileEntry>;
  defaults?: ProfileEntry;
}

export const DEFAULT_PROFILE_ENTRY = {
  component: false,
  liveText: false,
} satisfies Required<Pick<ProfileEntry, "component" | "liveText">>;

/**
 * A candidate listed in `profile.candidates` uses that entry; anything else
 * (an unmatched node, or a matched candidate the profile doesn't mention)
 * falls back to `profile.defaults`, then to the hardcoded default. `name` has
 * no fallback here — an absent name is resolved by the caller, which knows
 * the node's own id and can fall back to that.
 */
export function resolveProfileEntry(
  profile: Profile | undefined,
  candidateId: string | null,
): ProfileEntry {
  const defaults = profile?.defaults ?? {};
  const specific = candidateId !== null ? profile?.candidates?.[candidateId] : undefined;

  return {
    name: specific?.name ?? defaults.name,
    component: specific?.component ?? defaults.component ?? DEFAULT_PROFILE_ENTRY.component,
    liveText: specific?.liveText ?? defaults.liveText ?? DEFAULT_PROFILE_ENTRY.liveText,
  };
}
