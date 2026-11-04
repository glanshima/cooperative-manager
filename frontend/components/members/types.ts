/** Minimal shape for the Next-of-Kin member picker -- same fields as
 * Member.next_of_kin_member (schemas.py's NextOfKinMemberSummary), plus
 * whatever listMembers/search already returns (a full Member, but only
 * these fields are used here). */
export type NokMemberOption = { id: string; psn: string; name: string; phone?: string | null };
