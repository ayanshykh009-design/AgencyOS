// Framework-free composer-draft rule shared by the conversations panel.
// Extracted so the rule is unit-testable in the node test environment.

/**
 * Decide whether the composer draft may be cleared after a completed Record
 * Reply mutation.
 *
 * Clear ONLY when all three hold:
 * - the user never navigated away from the thread the mutation targeted
 *   (navigation context must match), AND
 * - the current draft is exactly what was submitted
 *   (the user has not typed something new — e.g. after the request resolved
 *   late, an unrelated draft must survive).
 *
 * Returns true → clear the composer. False → leave the composer untouched.
 */
export function shouldClearComposerAfter(
  navigationMatchesMutationContext: boolean,
  currentDraft: string,
  submittedDraft: string
): boolean {
  return navigationMatchesMutationContext && currentDraft === submittedDraft;
}
